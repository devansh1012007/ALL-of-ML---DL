"""Observability (plan H3): health, readiness, metrics, request logs.

The question "what is the queue doing" has to be answerable without a
database shell. Three endpoints answer it:

* ``/healthz`` - the process is up and the database answers;
* ``/readyz`` - the schema is at the revision the code expects, so a
  deployment that forgot its migration says so here instead of failing on
  the first request;
* ``/metrics`` - the Prometheus text format: the queue depth by status, the
  run durations, the failures by model, the predict latency of this process
  and the number of live workers.

The request log middleware writes one JSON line per request with a request
id (echoed back in ``X-Request-ID``) and, when the path carries one, the run
id - so a user's report of a failed run can be grepped end to end.
"""

from __future__ import annotations

import json
import math
import logging
import re
import time
import uuid
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import DeploymentStat, TrainingRun

logger = logging.getLogger("observability")
# The access log is the point of this module: the logger owns its level,
# because the root logger of a deployment is routinely left at WARNING (the
# default of ``basicConfig``), which would swallow every request line.
logger.setLevel(logging.INFO)

router = APIRouter()

# The id of the request, bound by the middleware and read by the log lines.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# The path of a run: /api/v1/ml/runs/{id}/... in every spelling the API has.
_RUN_PATH = re.compile(r"/runs/(\d+)")

# The predict latencies of this process: (timestamp, seconds). A process-
# local ring is the Prometheus norm for a latency histogram; the queue and
# the failure counters below come from the database and are global.
_PREDICT_LATENCIES: Deque[Tuple[float, float]] = deque(maxlen=1000)


def record_predict_latency(seconds: float) -> None:
    """One predict finished; remember how long it took."""
    _PREDICT_LATENCIES.append((time.time(), seconds))


_RUN_STATUS = ("queued", "running", "completed", "failed", "cancelled")


async def _queue_depth(db: AsyncSession) -> Dict[str, int]:
    rows = await db.execute(
        select(TrainingRun.status, func.count(TrainingRun.id)).group_by(TrainingRun.status)
    )
    return {status: count for status, count in rows.all()}


async def _run_durations(db: AsyncSession) -> Dict[str, Any]:
    """Sum and count of the wall seconds of the finished runs."""
    row = (
        await db.execute(
            select(func.count(TrainingRun.id), func.sum(TrainingRun.wall_seconds)).where(
                TrainingRun.wall_seconds.isnot(None)
            )
        )
    ).first()
    count, total = row if row else (0, None)
    return {"count": count or 0, "sum": float(total or 0.0)}


async def _failures_by_model(db: AsyncSession) -> Dict[str, int]:
    rows = await db.execute(
        select(TrainingRun.model_name, func.count(TrainingRun.id))
        .where(TrainingRun.status == "failed")
        .group_by(TrainingRun.model_name)
    )
    return {model: count for model, count in rows.all()}


async def _predict_totals(db: AsyncSession) -> Dict[str, Any]:
    """The predict counters of the last 24 hours, from the hourly stats."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:00:00")
    row = (
        await db.execute(
            select(
                func.count(DeploymentStat.id),
                func.sum(DeploymentStat.requests),
                func.sum(DeploymentStat.rows),
                func.sum(DeploymentStat.errors),
            ).where(DeploymentStat.hour >= since)
        )
    ).first()
    _hours, requests, rows_sent, errors = row if row else (0, 0, 0, 0)
    return {
        "requests": int(requests or 0),
        "rows": int(rows_sent or 0),
        "errors": int(errors or 0),
    }


async def _live_workers(db: AsyncSession) -> int:
    """The workers that wrote a heartbeat within the stale limit."""
    from .main import TRAINING_STALE_SECONDS

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=TRAINING_STALE_SECONDS)
    row = await db.execute(
        select(func.count(func.distinct(TrainingRun.worker_id))).where(
            TrainingRun.status == "running",
            TrainingRun.heartbeat_at.isnot(None),
            TrainingRun.heartbeat_at > cutoff,
        )
    )
    return int(row.scalar_one() or 0)


def _latency_summary() -> Dict[str, Any]:
    """The predict latency of this process, over the ring's window."""
    now = time.time()
    recent = [seconds for ts, seconds in _PREDICT_LATENCIES if now - ts < 3600]
    if not recent:
        return {"count": 0}
    ordered = sorted(recent)
    def _quantile(fraction: float) -> float:
        # The nearest-rank method: the smallest value whose rank covers the
        # fraction of the samples (ceil(fraction * n), one-based).
        rank = max(1, math.ceil(fraction * len(ordered)))
        return ordered[rank - 1]
    return {
        "count": len(ordered),
        "sum": sum(ordered),
        "p50": _quantile(0.50),
        "p95": _quantile(0.95),
    }


def _prometheus(samples: Dict[str, Any]) -> str:
    """Render the samples in the Prometheus text format."""
    lines = []

    def gauge(name: str, help_text: str, value, labels: Optional[Dict[str, str]] = None):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        label_text = ""
        if labels:
            rendered = ",".join(f'{key}="{value}"' for key, value in labels.items())
            label_text = "{" + rendered + "}"
        lines.append(f"{name}{label_text} {value}")

    depth: Dict[str, int] = samples["queue_depth"]
    for status in _RUN_STATUS:
        gauge(
            "ml_queue_depth",
            "Training runs by state in the queue.",
            depth.get(status, 0),
            {"status": status},
        )
    durations = samples["durations"]
    gauge("ml_run_seconds_sum", "Sum of the wall seconds of the finished runs.", round(durations["sum"], 3))
    gauge("ml_run_seconds_count", "Finished runs with a recorded wall time.", durations["count"])
    failures: Dict[str, int] = samples["failures"]
    for model, count in sorted(failures.items()):
        gauge("ml_run_failures_total", "Failed runs by model.", count, {"model": model})
    gauge("ml_run_failures_total", "Failed runs by model.", sum(failures.values()))
    predict = samples["predict"]
    gauge("ml_predict_requests_total", "Predict requests of the last 24 hours.", predict["requests"])
    gauge("ml_predict_rows_total", "Predicted rows of the last 24 hours.", predict["rows"])
    gauge("ml_predict_errors_total", "Predict errors of the last 24 hours.", predict["errors"])
    latency = samples["latency"]
    gauge("ml_predict_latency_seconds_count", "Predict handled by this process in the last hour.", latency.get("count", 0))
    if latency.get("count"):
        gauge("ml_predict_latency_seconds_sum", "Sum of the predict latency of this process.", round(latency["sum"], 4))
        gauge("ml_predict_latency_seconds{quantile=\"0.5\"}", "The predict latency of this process.", round(latency["p50"], 4))
        gauge("ml_predict_latency_seconds{quantile=\"0.95\"}", "The predict latency of this process.", round(latency["p95"], 4))
    gauge("ml_live_workers", "Workers that wrote a heartbeat within the stale limit.", samples["live_workers"])
    lines.append("")
    return "\n".join(lines)


async def _collect(db: AsyncSession) -> Dict[str, Any]:
    return {
        "queue_depth": await _queue_depth(db),
        "durations": await _run_durations(db),
        "failures": await _failures_by_model(db),
        "predict": await _predict_totals(db),
        "latency": _latency_summary(),
        "live_workers": await _live_workers(db),
    }


@router.get("/healthz")
async def healthz(db: AsyncSession = Depends(get_db)):
    """The process is up and the database answers."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)):
    """The schema is at the revision the code expects."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    row = (await db.execute(text("SELECT version_num FROM alembic_version"))).first()
    current = row[0] if row else None
    if current != head:
        return Response(
            content=json.dumps({"status": "migrating", "at": current, "expected": head}),
            status_code=503,
            media_type="application/json",
        )
    return {"status": "ok", "revision": current}


@router.get("/metrics")
async def metrics(db: AsyncSession = Depends(get_db)):
    """The counters of the plan, in the Prometheus text format."""
    samples = await _collect(db)
    return Response(content=_prometheus(samples), media_type="text/plain; version=0.0.4")


class RequestLogMiddleware:
    """One JSON log line per request, with the request and the run id.

    The request id is a short uuid; the client may hand one in via
    ``X-Request-ID`` and see the same one back. The run id is taken from the
    path when the request is about a run, so the line of a failing predict
    can be matched with the line of the training that produced the model.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"x-request-id", b"").decode("latin-1").strip()
        request_id = supplied[:64] if supplied else uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        run_match = _RUN_PATH.search(scope.get("path", ""))
        run_id = run_match.group(1) if run_match else None
        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_with_logging(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = dict(message, headers=response_headers)
            await send(message)

        try:
            await self.app(scope, receive, send_with_logging)
        finally:
            request_id_var.reset(token)
            elapsed_ms = (time.perf_counter() - started) * 1000
            path = scope.get("path", "")
            # The metrics and health endpoints would double the noise for
            # every scraper; they are logged only when they are slow.
            if not path.startswith(("/healthz", "/readyz", "/metrics")) or elapsed_ms > 1000:
                logger.info(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "request_id": request_id,
                    "run_id": run_id,
                    "method": scope.get("method", ""),
                    "path": path,
                    "status": status_holder["status"],
                    "duration_ms": round(elapsed_ms, 1),
                }))
