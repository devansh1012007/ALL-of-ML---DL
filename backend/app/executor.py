"""The execution layer: who runs a claimed run, and how (plans B1, B2, B3).

The database queue stays exactly what it was - the rows of ``training_runs``
are the state, the claim is one atomic UPDATE. What changes is the *how*:

* ``ThreadExecutor`` - today's behaviour: ``train_model`` in a thread of the
  worker process. It cannot be killed, a cancel frees the slot only when the
  thread ends, and a segfault takes the worker down. It is the default,
  because the test suite (which monkeypatches ``train_model``) and the tiny
  deployments rely on it.
* ``SubprocessExecutor`` - one fresh interpreter per training
  (``python -m backend.app.run_training --run-id N``). The child reads the
  stored request from the database itself, streams its progress as JSON
  lines on stdout, writes its result to a file, and can be **killed**:
  the wall clock and the memory limits are enforceable, a cancel frees the
  slot at once, and a crash in native code takes down one child and not the
  worker.

The choice is ``TRAINING_EXECUTOR`` (``thread`` | ``subprocess``). The
interface is the seam the plan keeps talking about: a Rust (or any) runner
that speaks the same JSON contract replaces a Python trainer one model at a
time, without touching the queue, the quotas or the API.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .progress import DatabaseSink, LineReporter, NullReporter, Reporter

# The states a run row can be in while a child works on it.
_CANCELLED = "cancelled"


@dataclass
class Limits:
    """What one run may consume. The numbers come from the owner's quota."""

    max_run_seconds: Optional[float] = None
    max_run_memory_mb: Optional[float] = None
    cpu_threads: Optional[int] = None


@dataclass
class ExecResult:
    """What an executor hands back to the queue."""

    status: str  # completed | failed | cancelled
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifact: Optional[Dict[str, Any]] = None
    charts: Optional[Dict[str, Any]] = None
    dataset_source: Optional[str] = None
    dataset_tag: Optional[str] = None
    wall_seconds: Optional[float] = None
    resource: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


def _thread_train_kwargs(payload, storage_path: Optional[str]) -> List[Any]:
    """The positional arguments of ``train_model``, in its order.

    One place, so the thread executor and the child cannot disagree about
    the order: the 19 positional parameters of ``train_model``.
    """
    return [
        payload.model_name,
        storage_path,
        payload.hf_dataset_url,
        payload.label_column,
        payload.test_size,
        payload.random_state,
        payload.hyperparameters or {},
        payload.sep,
        payload.usecols,
        payload.mode,
        payload.optimize_metric,
        payload.env_id,
        payload.model_candidates,
        payload.preset,
        payload.task_type,
        payload.cv_folds,
        payload.preprocessing,
        payload.split,
        payload.time_column,
    ]


class Executor:
    """The interface of plan B1: run a claimed run, report progress."""

    name = "abstract"

    async def execute(
        self,
        run_id: int,
        payload,  # a TrainRequest
        storage_path: Optional[str],
        limits: Limits,
        sink: DatabaseSink,
    ) -> ExecResult:
        raise NotImplementedError


class ThreadExecutor(Executor):
    """``train_model`` in a thread of the worker process (today's behaviour).

    A cancel frees the slot only when the thread ends - the honest caveat of
    this executor, documented in the plan (B3) and unchanged here.
    """

    name = "thread"

    async def execute(self, run_id, payload, storage_path, limits, sink):
        from fastapi.concurrency import run_in_threadpool

        # Through the main module, on purpose: the test suite (and any
        # deployment that wants a hook) patches ``main.train_model``, and the
        # executor must call what the process patched, not a stale import.
        from . import main as main_module

        train_model = main_module.train_model

        reporter = await sink.reporter()
        sink.append("phase", {"phase": "training", "executor": self.name})
        started = time.monotonic()
        try:
            metrics, dataset_source, dataset_tag, artifact = await run_in_threadpool(
                train_model, *_thread_train_kwargs(payload, storage_path)
            )
        except Exception as exc:  # noqa: BLE001 - the run carries the reason
            from .main import _public_error

            return ExecResult(
                status="failed",
                metrics={"error": _public_error(exc)},
                wall_seconds=time.monotonic() - started,
            )
        wall = time.monotonic() - started
        charts = None
        if isinstance(metrics, dict):
            charts = metrics.pop("_charts", None)
        return ExecResult(
            status="completed",
            metrics=metrics,
            artifact=artifact,
            charts=charts,
            dataset_source=dataset_source,
            dataset_tag=dataset_tag,
            wall_seconds=wall,
        )


class SubprocessExecutor(Executor):
    """One fresh interpreter per training (plan B2).

    The parent is the only writer of the run state. The child reads its
    request from the database, streams events on stdout, writes
    ``result.json``, and dies on the parent's word: the wall clock, the
    memory sampling and a cancel all end in ``terminate()`` and, after a
    grace of ten seconds, ``kill()``.
    """

    name = "subprocess"

    CANCEL_POLL_SECONDS = 1.0
    EVENT_FLUSH_SECONDS = 1.0
    TERMINATE_GRACE_SECONDS = 10.0

    async def execute(self, run_id, payload, storage_path, limits, sink):
        from .settings import REPO_ROOT

        started = time.monotonic()
        scratch = Path(tempfile.mkdtemp(prefix=f"run_{run_id}_", dir=self._scratch_root()))
        environment = self._child_environment(limits)
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "backend.app.run_training",
                "--run-id",
                str(run_id),
                cwd=str(scratch),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1 << 20,  # a line of events may be big, but not endless
            )
        except OSError as exc:
            shutil.rmtree(scratch, ignore_errors=True)
            return ExecResult(
                status="failed",
                metrics={"error": f"The training process could not start: {exc}"},
                wall_seconds=time.monotonic() - started,
            )

        sink.append("phase", {"phase": "training", "executor": self.name, "pid": process.pid})
        pending_events: List[Dict[str, Any]] = []
        result_payload: Optional[Dict[str, Any]] = None
        death_reason: Optional[str] = None

        async def read_lines() -> None:
            nonlocal result_payload
            assert process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    pending_events.append({"kind": "log", "payload": {"message": line[:2000]}})
                    continue
                if message.get("kind") == "result":
                    result_payload = message.get("payload")
                else:
                    pending_events.append(message)

        async def flush_events() -> None:
            while True:
                await asyncio.sleep(self.EVENT_FLUSH_SECONDS)
                if pending_events:
                    batch, pending_events[:] = pending_events[:], []
                    for message in batch:
                        sink.append(message.get("kind", "log"), message.get("payload"))
                    await sink.flush()

        async def enforce_limits_and_cancel() -> Optional[str]:
            """Kill the child on a cancel, on the wall clock, on the memory."""
            loop = asyncio.get_running_loop()
            next_memory_check = 0.0
            while True:
                await asyncio.sleep(self.CANCEL_POLL_SECONDS)
                status = await self._status_of(run_id)
                if status == _CANCELLED:
                    return "cancelled"
                if (
                    limits.max_run_seconds is not None
                    and time.monotonic() - started > limits.max_run_seconds
                ):
                    return "The wall-clock limit of the run is exceeded."
                now = loop.time()
                if (
                    limits.max_run_memory_mb is not None
                    and now >= next_memory_check
                ):
                    next_memory_check = now + 1.0
                    rss_mb = self._child_rss_mb(process.pid)
                    if rss_mb is not None and rss_mb > limits.max_run_memory_mb:
                        return (
                            f"The memory limit is exceeded: the child held {rss_mb:.0f} MiB, "
                            f"the limit is {limits.max_run_memory_mb:.0f} MiB."
                        )

        reader = asyncio.create_task(read_lines())
        flusher = asyncio.create_task(flush_events())
        watcher = asyncio.create_task(enforce_limits_and_cancel())

        async def read_errors() -> str:
            assert process.stderr is not None
            chunks = []
            async for raw in process.stderr:
                chunks.append(raw.decode("utf-8", "replace"))
            return "".join(chunks)

        error_reader = asyncio.create_task(read_errors())

        done, _pending = await asyncio.wait(
            {asyncio.create_task(process.wait()), watcher},
            return_when=asyncio.FIRST_COMPLETED,
        )
        reason: Optional[str] = None
        for task in done:
            outcome = task.result()
            if isinstance(outcome, str):
                reason = outcome
        if reason is not None and process.returncode is None:
            await self._stop(process)
            sink.append("log", {"message": f"The training was stopped: {reason}"})

        watcher.cancel()
        flusher.cancel()
        try:
            await asyncio.wait_for(process.wait(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        await reader
        child_stderr = await error_reader
        # Whatever the child printed in its last second still lands in the
        # table: one final, synchronous flush.
        for message in pending_events:
            sink.append(message.get("kind", "log"), message.get("payload"))
        pending_events[:] = []
        await sink.flush()
        shutil.rmtree(scratch, ignore_errors=True)

        wall = time.monotonic() - started
        if reason == "cancelled":
            return ExecResult(status="cancelled", wall_seconds=wall)
        if reason is not None:
            return ExecResult(
                status="failed",
                metrics={"error": reason},
                wall_seconds=wall,
            )
        if result_payload is not None and result_payload.get("status") == "failed":
            # The child caught its own failure and said so; its message is
            # the answer, the exit code is a duplicate of the same news.
            return ExecResult(
                status="failed",
                metrics=result_payload.get("metrics") or {"error": "The training failed."},
                wall_seconds=wall,
            )
        if process.returncode != 0:
            tail = "\n".join(child_stderr.strip().splitlines()[-5:])[:2000]
            return ExecResult(
                status="failed",
                metrics={
                    "error": (
                        f"The training process died with code {process.returncode}."
                        + (f" The child said: {tail}" if tail else "")
                    )
                },
                wall_seconds=wall,
            )
        if result_payload is None:
            return ExecResult(
                status="failed",
                metrics={"error": "The training process wrote no result."},
                wall_seconds=wall,
            )
        return ExecResult(
            status=result_payload.get("status", "completed"),
            metrics=result_payload.get("metrics") or {},
            artifact=result_payload.get("artifact"),
            charts=result_payload.get("charts"),
            dataset_source=result_payload.get("dataset_source"),
            dataset_tag=result_payload.get("dataset_tag"),
            wall_seconds=wall,
            resource=result_payload.get("resource") or {},
        )

    # --- the pieces -------------------------------------------------------

    def _scratch_root(self) -> str:
        from .model_training import MODEL_DIR

        Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)
        return str(MODEL_DIR)

    def _child_environment(self, limits: Limits) -> Dict[str, str]:
        environment = dict(os.environ)
        threads = str(limits.cpu_threads) if limits.cpu_threads else "2"
        # One run must not take every core of the machine (plan B2).
        environment.update({
            "OMP_NUM_THREADS": threads,
            "MKL_NUM_THREADS": threads,
            "OPENBLAS_NUM_THREADS": threads,
            "NUMEXPR_NUM_THREADS": threads,
        })
        return environment

    async def _status_of(self, run_id: int) -> Optional[str]:
        from sqlalchemy import select

        from .database import AsyncSessionLocal
        from .models import TrainingRun

        async with AsyncSessionLocal() as session:
            row = await session.execute(
                select(TrainingRun.status).where(TrainingRun.id == run_id)
            )
            value = row.scalar_one_or_none()
            return value if isinstance(value, str) else None

    def _child_rss_mb(self, pid: int) -> Optional[float]:
        try:
            import psutil

            return psutil.Process(pid).memory_info().rss / (1024 * 1024)
        except Exception:  # noqa: BLE001 - no psutil, no process: no limit
            return None

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        """terminate(), ten seconds of grace, then kill() (plan B2)."""
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=self.TERMINATE_GRACE_SECONDS)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass


_EXECUTOR: Optional[Executor] = None


def choose_executor() -> Executor:
    """The executor of this process, chosen once (plan B1)."""
    global _EXECUTOR
    if _EXECUTOR is None:
        choice = (os.getenv("TRAINING_EXECUTOR") or "thread").strip().lower()
        if choice == "subprocess":
            _EXECUTOR = SubprocessExecutor()
        elif choice == "thread":
            _EXECUTOR = ThreadExecutor()
        else:
            raise RuntimeError(
                f"TRAINING_EXECUTOR={choice!r} is not one of ['thread', 'subprocess']."
            )
    return _EXECUTOR
