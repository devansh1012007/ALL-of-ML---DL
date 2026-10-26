"""The progress of a run: events, reporters, and the cap (plan B4).

A user watching a ten-minute job needs to know it is alive and converging.
The events travel one of two ways:

* the **thread executor** writes them straight into ``run_events`` through
  :class:`DatabaseSink`;
* the **subprocess executor** hands the child a :class:`LineReporter`, the
  child prints one JSON object per line on its standard output, and the
  parent batches the lines into the table.

Both reporters speak one small protocol — ``phase``, ``metric``, ``log`` —
so a trainer does not know which executor runs it.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RunEvent

# The events of one run are capped: the last ones stay, the older ones are
# deleted as new ones arrive. A chatty trainer must not fill the disk with
# progress.
MAX_EVENTS_PER_RUN = int(__import__("os").getenv("MAX_EVENTS_PER_RUN", "2000"))


class Reporter:
    """What a trainer may call to say what it is doing.

    Everything is best-effort: a reporter that cannot write (a closed pipe,
    a full table) must never fail a training that is otherwise fine.
    """

    def phase(self, name: str, detail: Optional[Dict[str, Any]] = None) -> None:
        raise NotImplementedError

    def metric(self, values: Dict[str, Any]) -> None:
        raise NotImplementedError

    def log(self, message: str) -> None:
        raise NotImplementedError

    def close(self) -> None:  # noqa: B027 - a default no-op is the point
        pass


class NullReporter(Reporter):
    """The reporter of the tests and of the callers that want silence."""

    def phase(self, name, detail=None):
        pass

    def metric(self, values):
        pass

    def log(self, message):
        pass


class LineReporter(Reporter):
    """One JSON object per line on a stream (the child process uses stdout).

    The parent reads the lines and batches them into the table, so the child
    never touches the database - it has no business being a writer of the
    state (plan B2).
    """

    def __init__(self, stream=None):
        self._stream = stream or sys.stdout

    def _emit(self, kind: str, payload: Optional[Dict[str, Any]]) -> None:
        line = json.dumps(
            {"kind": kind, "payload": payload, "ts": time.time()}, default=str
        )
        try:
            self._stream.write(line + "\n")
            self._stream.flush()
        except (ValueError, OSError):
            # The parent is gone or the pipe is closed: the training continues.
            pass

    def phase(self, name, detail=None):
        self._emit("phase", dict(detail or {}, phase=name))

    def metric(self, values):
        self._emit("metric", values)

    def log(self, message):
        self._emit("log", {"message": str(message)[:2000]})


class DatabaseSink:
    """The parent side of the events: a batched writer of ``run_events``.

    Events are appended in memory and flushed as a batch. The sink opens its
    own short session per flush: the executor runs on the event loop, the
    trainers run in threads, and a session shared between the two is a
    race that only shows up under load. The cap keeps the last
    ``MAX_EVENTS_PER_RUN`` events of the run.
    """

    def __init__(self, run_id: int):
        self._run_id = run_id
        self._buffer: List[Dict[str, Any]] = []
        self._next_seq: Optional[int] = None

    async def _reserve_seq(self, db: AsyncSession) -> int:
        if self._next_seq is None:
            row = await db.execute(
                select(func.max(RunEvent.seq)).where(RunEvent.run_id == self._run_id)
            )
            self._next_seq = int(row.scalar_one() or 0) + 1
        seq = self._next_seq
        self._next_seq += 1
        return seq

    def append(self, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Queue one event; the flush writes it with its neighbours."""
        self._buffer.append({"kind": kind, "payload": payload})

    async def flush(self) -> int:
        """Write the queued events on a session of their own."""
        if not self._buffer:
            return 0
        from .database import AsyncSessionLocal

        written = 0
        async with AsyncSessionLocal() as db:
            for event in self._buffer:
                seq = await self._reserve_seq(db)
                db.add(
                    RunEvent(
                        run_id=self._run_id,
                        seq=seq,
                        ts=datetime.now(timezone.utc),
                        kind=event["kind"],
                        payload=event["payload"],
                    )
                )
                written += 1
            self._buffer.clear()
            await db.commit()
        await self._enforce_cap()
        return written

    async def _enforce_cap(self) -> None:
        from .database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(
                    select(func.count(RunEvent.id)).where(RunEvent.run_id == self._run_id)
                )
            ).scalar_one()
            if total <= MAX_EVENTS_PER_RUN:
                return
            keep_from = total - MAX_EVENTS_PER_RUN
            await db.execute(
                delete(RunEvent).where(
                    RunEvent.run_id == self._run_id, RunEvent.seq <= keep_from
                )
            )
            await db.commit()

    async def reporter(self) -> "SyncReporterBridge":
        """A synchronous reporter that queues into this sink.

        The trainers run in threads (the thread executor) and call the
        reporter synchronously; the bridge only queues, so it needs no
        database access and is safe to call from anywhere.
        """
        return SyncReporterBridge(self)


class SyncReporterBridge(Reporter):
    """The trainer-facing face of a sink: synchronous, thread-safe enough.

    Every call only appends to a list, which the executor's event loop drains
    on its own cadence.
    """

    def __init__(self, sink: DatabaseSink):
        self._sink = sink

    def phase(self, name, detail=None):
        self._sink.append("phase", dict(detail or {}, phase=name))

    def metric(self, values):
        self._sink.append("metric", dict(values))

    def log(self, message):
        self._sink.append("log", {"message": str(message)[:2000]})


async def events_after(db: AsyncSession, run_id: int, after: int, limit: int = 500):
    """The events of the run with a seq above ``after``, oldest first."""
    result = await db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.seq > after)
        .order_by(RunEvent.seq)
        .limit(max(1, min(int(limit), 1000)))
    )
    return result.scalars().all()
