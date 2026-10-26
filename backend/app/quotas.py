"""The quota model and its enforcement (plans A3, A4, A5).

Why this module exists
----------------------
Nothing limited what a user could take: one user could queue a thousand runs
and every other user would wait behind them, fill the disk with datasets and
artifacts, and spend every core for days. The limits are **data an admin
edits** (two tables: a profile per kind of user, an override for the
exceptions), not constants in the code, and the system must also **measure
what it limits** - a derived sum cannot drift from the truth the way a
maintained counter does after a crash.

Where the limits are enforced (plan A4): the submit-time checks answer before
a run exists; the claim-time re-check catches a profile that changed while a
run waited; the predict checks bound one request and the request rate. Every
refusal carries the ``quota`` object (name, limit, used, resets_at) so the
interface can show the reason and the reset time instead of an opaque 403.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Dataset, QuotaProfile, TrainingRun, User, UserQuotaOverride

# The categories a fresh "free" profile may train (plan A3): the tabular
# families are on, the compute-heavy ones are off until an admin enables
# them, because those are the entries that can cost real money or block the
# machine. ``QUOTA_FREE_CATEGORIES`` is the deployment-level way to enable a
# family without editing the database (a demo box turns everything on; a
# private lab keeps the tabular ones).
FREE_CATEGORIES = [
    category.strip()
    for category in os.getenv(
        "QUOTA_FREE_CATEGORIES",
        "classification,regression,clustering,autoencoder,time-series",
    ).split(",")
    if category.strip()
]

# The names of the profiles seeded at startup (plan A3). "unlimited" is the
# absence of numbers (NULL means unlimited) and is what the admins get.
PROFILE_FREE = {
    "name": "free",
    "max_concurrent_runs": 1,
    "max_queued_runs": 5,
    "max_runs_per_day": 20,
    "max_run_seconds": 600,
    "max_run_memory_mb": 2048,
    "max_cpu_seconds_per_month": 7200,
    "max_storage_bytes": 500 * 1024 * 1024,
    "max_datasets": 10,
    "max_upload_bytes": 50 * 1024 * 1024,
    "max_rows": 500000,
    "max_predict_rows_per_request": 1000,
    "max_predict_requests_per_minute": 60,
    "allowed_categories": FREE_CATEGORIES,
    "gpu_allowed": False,
}
PROFILE_STANDARD = {
    "name": "standard",
    "max_concurrent_runs": 2,
    "max_queued_runs": 20,
    "max_runs_per_day": 100,
    "max_run_seconds": 3600,
    "max_run_memory_mb": 4096,
    "max_cpu_seconds_per_month": 30000,
    "max_storage_bytes": 5 * 1024 * 1024 * 1024,
    "max_datasets": 50,
    "max_upload_bytes": 200 * 1024 * 1024,
    "max_rows": 2000000,
    "max_predict_rows_per_request": 5000,
    "max_predict_requests_per_minute": 300,
    "allowed_categories": None,  # NULL: every category
    "gpu_allowed": False,
}
PROFILE_UNLIMITED = {"name": "unlimited"}

QUOTA_COLUMNS = [
    "max_concurrent_runs",
    "max_queued_runs",
    "max_runs_per_day",
    "max_run_seconds",
    "max_run_memory_mb",
    "max_cpu_seconds_per_month",
    "max_storage_bytes",
    "max_datasets",
    "max_upload_bytes",
    "max_rows",
    "max_predict_rows_per_request",
    "max_predict_requests_per_minute",
    "allowed_categories",
    "gpu_allowed",
    # The retention of the artifacts (plan H1) rides the same resolution:
    # the override wins, else the profile, else "keep everything".
    "artifact_keep_runs",
    "artifact_keep_days",
]


class QuotaRefusal(Exception):
    """A limit was hit; the body carries the quota object of plan A4.

    ``detail`` is what ``HTTPException(detail=...)`` receives: the message
    and the ``quota`` object (name, limit, used, resets_at), so the interface
    can show the reason and the reset time.
    """

    def __init__(
        self,
        name: str,
        limit: Optional[int],
        used: Any,
        message: Optional[str] = None,
        resets_at: Optional[datetime] = None,
        status_code: int = 429,
    ):
        self.name = name
        self.limit = limit
        self.used = used
        self.status_code = status_code
        quota: Dict[str, Any] = {"name": name, "limit": limit, "used": used}
        if resets_at is not None:
            quota["resets_at"] = resets_at.isoformat()
        self.quota = quota
        self.detail = {
            "message": message or f"The limit '{name}' was reached.",
            "quota": quota,
        }
        super().__init__(self.detail["message"])


# --- the effective quota ------------------------------------------------------


async def _default_profile(db: AsyncSession) -> QuotaProfile:
    """The profile a user without one gets: "free" (plan A3)."""
    profile = (
        await db.execute(select(QuotaProfile).where(QuotaProfile.name == "free"))
    ).scalars().first()
    if profile is None:
        # The seeding has not run (a test that never started the app): a
        # profile built in memory keeps the checks working.
        profile = QuotaProfile(**PROFILE_FREE)
    return profile


async def effective_quota(db: AsyncSession, user: User) -> Dict[str, Any]:
    """The limits of a user: the override where set, else the profile value.

    This is the only place a limit is resolved (plan A3), so there is exactly
    one definition of what a user may do.
    """
    profile: Optional[QuotaProfile] = None
    if user.quota_profile_id is not None:
        profile = await db.get(QuotaProfile, user.quota_profile_id)
    if profile is None:
        profile = await _default_profile(db)
    override = (
        await db.execute(
            select(UserQuotaOverride).where(UserQuotaOverride.user_id == user.id)
        )
    ).scalars().first()

    quota: Dict[str, Any] = {}
    for column in QUOTA_COLUMNS:
        value = getattr(override, column, None) if override is not None else None
        if value is None:
            value = getattr(profile, column, None)
        quota[column] = value
    quota["profile_name"] = getattr(profile, "name", "free")
    return quota


async def seed_quota_profiles(db: AsyncSession) -> None:
    """Create the three profiles once, at startup (plan A3)."""
    for spec in (PROFILE_FREE, PROFILE_STANDARD, PROFILE_UNLIMITED):
        existing = (
            await db.execute(select(QuotaProfile).where(QuotaProfile.name == spec["name"]))
        ).scalars().first()
        if existing is None:
            db.add(QuotaProfile(**spec))
    await db.commit()


# --- the usage accounting (plan A5) -------------------------------------------


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_month(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def user_usage(db: AsyncSession, user: User) -> Dict[str, Any]:
    """What the system limits, measured (plan A5).

    The storage a user holds is the sum of the sizes of the datasets and the
    artifacts of the runs - a derived sum, so it cannot drift from the truth
    the way a maintained counter does after a crash or a manual deletion.
    """
    now = datetime.now(timezone.utc)
    day_start = _start_of_day(now)
    month_start = _start_of_month(now)

    storage_datasets = (
        await db.execute(
            select(func.coalesce(func.sum(Dataset.size_bytes), 0)).where(
                Dataset.owner_id == user.id
            )
        )
    ).scalar() or 0
    storage_artifacts = (
        await db.execute(
            select(func.coalesce(func.sum(TrainingRun.artifact_bytes), 0)).where(
                TrainingRun.owner_id == user.id
            )
        )
    ).scalar() or 0
    datasets_count = (
        await db.execute(
            select(func.count(Dataset.id)).where(Dataset.owner_id == user.id)
        )
    ).scalar() or 0
    runs_today = (
        await db.execute(
            select(func.count(TrainingRun.id)).where(
                TrainingRun.owner_id == user.id,
                TrainingRun.created_at >= day_start,
                TrainingRun.job_kind == "train",
            )
        )
    ).scalar() or 0
    queued = (
        await db.execute(
            select(func.count(TrainingRun.id)).where(
                TrainingRun.owner_id == user.id, TrainingRun.status == "queued"
            )
        )
    ).scalar() or 0
    running = (
        await db.execute(
            select(func.count(TrainingRun.id)).where(
                TrainingRun.owner_id == user.id, TrainingRun.status == "running"
            )
        )
    ).scalar() or 0
    cpu_month = (
        await db.execute(
            select(func.coalesce(func.sum(TrainingRun.cpu_seconds), 0)).where(
                TrainingRun.owner_id == user.id,
                TrainingRun.started_at >= month_start,
            )
        )
    ).scalar() or 0

    quota = await effective_quota(db, user)
    storage_bytes = int(storage_datasets + storage_artifacts)
    usage: Dict[str, Any] = {
        "runs_today": int(runs_today),
        "queued": int(queued),
        "running": int(running),
        "storage_bytes": storage_bytes,
        "datasets": int(datasets_count),
        "cpu_seconds_this_month": int(cpu_month or 0),
        "limits": {
            "max_runs_per_day": quota["max_runs_per_day"],
            "max_queued_runs": quota["max_queued_runs"],
            "max_concurrent_runs": quota["max_concurrent_runs"],
            "max_storage_bytes": quota["max_storage_bytes"],
            "max_datasets": quota["max_datasets"],
            "max_cpu_seconds_per_month": quota["max_cpu_seconds_per_month"],
        },
        "resets_at": {
            "max_runs_per_day": (_start_of_day(now) + timedelta(days=1)).isoformat(),
            "max_cpu_seconds_per_month": (
                (_start_of_month(now) + timedelta(days=32)).replace(day=1).isoformat()
            ),
        },
    }
    return usage


# --- the submit-time checks (plan A4) -----------------------------------------


async def check_submit_quota(
    db: AsyncSession,
    user: User,
    category: str,
    row_count: Optional[int],
) -> None:
    """Refuse a training before a run exists (plan A4).

    The checks answer immediately, at the moment the user submits: whether
    the category is allowed at all, whether the queue or the day is full,
    whether the dataset is bigger than the limit, and whether there is
    storage headroom left. Concurrency is a property of the moment of
    execution and is checked at claim time instead.
    """
    quota = await effective_quota(db, user)
    now = datetime.now(timezone.utc)

    allowed = quota.get("allowed_categories")
    if allowed is not None and category not in allowed:
        raise QuotaRefusal(
            "allowed_categories",
            None,
            category,
            message=(
                f"The category '{category}' is not enabled for this account. "
                "An administrator can enable it in the quota profile."
            ),
            status_code=403,
        )

    queued = (
        await db.execute(
            select(func.count(TrainingRun.id)).where(
                TrainingRun.owner_id == user.id,
                TrainingRun.status == "queued",
                TrainingRun.job_kind == "train",
            )
        )
    ).scalar() or 0
    if quota["max_queued_runs"] is not None and queued >= quota["max_queued_runs"]:
        raise QuotaRefusal(
            "max_queued_runs",
            quota["max_queued_runs"],
            queued,
            message=(
                f"You already have {queued} queued runs; wait for one to finish "
                "before queueing another."
            ),
        )

    day_start = _start_of_day(now)
    runs_today = (
        await db.execute(
            select(func.count(TrainingRun.id)).where(
                TrainingRun.owner_id == user.id,
                TrainingRun.created_at >= day_start,
                TrainingRun.job_kind == "train",
            )
        )
    ).scalar() or 0
    if quota["max_runs_per_day"] is not None and runs_today >= quota["max_runs_per_day"]:
        raise QuotaRefusal(
            "max_runs_per_day",
            quota["max_runs_per_day"],
            runs_today,
            message=f"You already started {runs_today} runs today.",
            resets_at=_start_of_day(now) + timedelta(days=1),
        )

    if row_count is not None and quota["max_rows"] is not None:
        if row_count > quota["max_rows"]:
            raise QuotaRefusal(
                "max_rows",
                quota["max_rows"],
                row_count,
                message=(
                    f"The dataset has {row_count} rows; the limit for this "
                    f"account is {quota['max_rows']}."
                ),
                status_code=413,
            )

    storage = await user_usage(db, user)
    used_bytes = storage["storage_bytes"]
    if quota["max_storage_bytes"] is not None and used_bytes >= quota["max_storage_bytes"]:
        raise QuotaRefusal(
            "max_storage_bytes",
            quota["max_storage_bytes"],
            used_bytes,
            message=(
                "Your storage is full: delete datasets or runs to free space "
                "before training again."
            ),
            status_code=403,
        )


async def check_upload_quota(
    db: AsyncSession,
    user: User,
    upload_bytes: int,
) -> None:
    """The upload checks of plan A4: bytes, dataset count, storage headroom."""
    quota = await effective_quota(db, user)
    if quota["max_upload_bytes"] is not None and upload_bytes > quota["max_upload_bytes"]:
        raise QuotaRefusal(
            "max_upload_bytes",
            quota["max_upload_bytes"],
            upload_bytes,
            message=f"The upload is {upload_bytes} bytes; the limit is {quota['max_upload_bytes']}.",
            status_code=413,
        )

    usage = await user_usage(db, user)
    datasets_count = usage["datasets"]
    if quota["max_datasets"] is not None and datasets_count >= quota["max_datasets"]:
        raise QuotaRefusal(
            "max_datasets",
            quota["max_datasets"],
            datasets_count,
            message=(
                f"You already have {datasets_count} datasets; delete one "
                "before uploading another."
            ),
            status_code=403,
        )

    if quota["max_storage_bytes"] is not None:
        headroom = quota["max_storage_bytes"] - usage["storage_bytes"]
        if upload_bytes > headroom:
            raise QuotaRefusal(
                "max_storage_bytes",
                quota["max_storage_bytes"],
                usage["storage_bytes"],
                message=(
                    f"The upload needs {upload_bytes} bytes and only {max(0, headroom)} "
                    "are left in your storage."
                ),
                status_code=403,
            )


# --- the predict checks (plan A4) ---------------------------------------------

# The per-user request rate of the predict endpoints: a sliding window in
# the memory of the process, like the login limiter of main.py (the shared
# store of plan A8 belongs to the identity phase).
_predict_attempts: Dict[str, deque] = defaultdict(deque)
_WINDOW_SECONDS = 60.0


def reset_predict_rate_limits() -> None:
    """Forget every recorded predict attempt (the test suite uses it)."""
    _predict_attempts.clear()


def check_predict_rate(user_id: int, quota: Dict[str, Any]) -> None:
    """Bound the predict requests per minute of one user (plan A4)."""
    limit = quota.get("max_predict_requests_per_minute")
    if not limit or limit <= 0:
        return
    now = time.monotonic()
    attempts = _predict_attempts[user_id]
    while attempts and now - attempts[0] > _WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= limit:
        raise QuotaRefusal(
            "max_predict_requests_per_minute",
            limit,
            len(attempts),
            message=(
                f"You already sent {len(attempts)} predict requests this minute; "
                "the limit for this account is "
                f"{limit}."
            ),
        )
    attempts.append(now)


def check_predict_rows(rows: int, quota: Dict[str, Any]) -> None:
    """Bound the rows of one predict request (plan A4)."""
    limit = quota.get("max_predict_rows_per_request")
    if limit and rows > limit:
        raise QuotaRefusal(
            "max_predict_rows_per_request",
            limit,
            rows,
            message=f"A predict request may carry at most {limit} rows, got {rows}.",
            status_code=413,
        )
