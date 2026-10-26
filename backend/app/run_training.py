"""One training, one interpreter: the child of the subprocess executor (B2).

The parent starts this module as::

    python -m backend.app.run_training --run-id N

The child reads the stored request from the database itself, so nothing
crosses the process boundary through pickling. It prints one JSON object
per line on its standard output - the progress events and, at the very end,
one ``result`` line - and writes ``result.json`` next to the artifact, so a
parent that died with the result still exists.

The parent is the only writer of the run state: this process never touches
``training_runs``. Its only writes are the event lines on stdout and the
result file. A ``TRAINING_RUNNER`` environment variable names a module with
an ``execute_run(request) -> dict`` function, which is how the tests give
the child a cheap fake runner - and how a non-Python runner could take over
one model at a time (the seam of plan B1).

Resource limits the child applies to itself (plan B2): ``RLIMIT_CPU`` as a
backstop behind the parent's wall-clock kill. The memory limit is the
parent's job (it samples the child with psutil); a process cannot be
trusted to limit itself out of existence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _apply_cpu_backstop(cpu_seconds: Optional[float]) -> None:
    """A hard stop for a child that ignores everything else.

    Only POSIX has resource limits for a child; on Windows the parent's
    wall clock and the memory sampling still work, and this is skipped.
    """
    if not cpu_seconds or cpu_seconds <= 0 or not hasattr(resource, "RLIMIT_CPU"):
        return
    soft = int(cpu_seconds)
    hard = int(cpu_seconds) + 5
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))
    except (ValueError, OSError):
        # A limit lower than the current usage would be refused; the parent
        # remains the authority.
        pass


def _load_runner():
    """The runner of the run: the real trainer, or the module TRAINING_RUNNER names."""
    custom = (os.getenv("TRAINING_RUNNER") or "").strip()
    if custom:
        module = __import__(custom, fromlist=["execute_run"])
        return module.execute_run
    from .model_training import train_model

    return train_model


async def _read_stored(run_id: int) -> Dict[str, Any]:
    from sqlalchemy import select

    from .database import AsyncSessionLocal
    from .models import TrainingRun

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(TrainingRun.request_payload).where(TrainingRun.id == run_id)
        )
        stored = row.scalar_one_or_none()
    if not stored:
        raise ValueError(f"The run {run_id} has no stored request.")
    return dict(stored)


def _train_positional(payload_dict: Dict[str, Any], storage_path: Optional[str]) -> list:
    """The 19 positional arguments of ``train_model``, from the stored request."""
    request = payload_dict["request"]
    from .main import TrainRequest

    payload = TrainRequest(**request)
    from .executor import _thread_train_kwargs

    return _thread_train_kwargs(payload, storage_path)


async def main_async(run_id: int) -> int:
    started = time.monotonic()
    out = sys.stdout

    def emit(kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        out.write(json.dumps({"kind": kind, "payload": payload}, default=str) + "\n")
        out.flush()

    emit("phase", {"phase": "starting"})
    stored = await _read_stored(run_id)
    storage_path = stored.get("storage_path")

    limits = (stored.get("limits") or {}) if isinstance(stored.get("limits"), dict) else {}
    _apply_cpu_backstop(limits.get("cpu_seconds"))
    if limits.get("cpu_threads"):
        threads = str(int(limits["cpu_threads"]))
        os.environ.setdefault("OMP_NUM_THREADS", threads)
        os.environ.setdefault("MKL_NUM_THREADS", threads)

    emit("phase", {"phase": "training"})
    runner = _load_runner()
    try:
        if getattr(runner, "__module__", "").endswith("model_training"):
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: runner(*_train_positional(stored, storage_path))
            )
            metrics, dataset_source, dataset_tag, artifact = result
            if isinstance(metrics, dict):
                charts = metrics.pop("_charts", None)
            else:
                charts = None
            result_payload = {
                "status": "completed",
                "metrics": metrics,
                "artifact": artifact,
                "charts": charts,
                "dataset_source": dataset_source,
                "dataset_tag": dataset_tag,
                "resource": {"wall_seconds": time.monotonic() - started},
            }
        else:
            # A custom runner (the tests' fake, or a future Rust runner that
            # speaks the JSON contract through a Python shim): it receives
            # the stored payload and returns the result dict itself.
            result_payload = await asyncio.get_running_loop().run_in_executor(
                None, lambda: runner(stored)
            )
            result_payload.setdefault("status", "completed")
    except Exception as exc:  # noqa: BLE001 - the parent carries the reason
        emit("result", {
            "status": "failed",
            "metrics": {"error": str(exc)[:2000]},
            "resource": {"wall_seconds": time.monotonic() - started},
        })
        return 1

    emit("phase", {"phase": "writing result"})
    # The result also lands in a file next to the artifact: a parent that
    # died after the child finished must not lose the work (plan B2).
    try:
        artifact_path = (result_payload.get("artifact") or {}).get("artifact_path")
        if artifact_path:
            result_file = Path(artifact_path) / "result.json"
        else:
            result_file = Path.cwd() / "result.json"
        result_file.write_text(json.dumps(result_payload, default=str), encoding="utf-8")
    except (OSError, TypeError):
        pass

    emit("result", result_payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args.run_id))
    except Exception as exc:  # noqa: BLE001 - the parent reads the exit code
        sys.stdout.write(
            json.dumps({
                "kind": "result",
                "payload": {"status": "failed", "metrics": {"error": str(exc)[:2000]}},
            }) + "\n"
        )
        sys.stdout.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
