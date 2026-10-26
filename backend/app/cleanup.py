"""Deletion and retention (plan H1).

A user who cannot delete what they made cannot be given a storage quota: the
space never comes back. This module holds the three pieces the plan asks for:

* **run deletion** - the run row, its artifact directory and its charts go
  together; a run that is queued or running refuses (cancel first), and a run
  that a deployment still serves refuses too (the deployment would 404 on its
  next predict);
* **retention** - a quota profile can keep the artifacts of the last N runs
  or of the last X days; the runs that fall out keep their metrics and show
  ``artifact_removed``, so the comparison view keeps its history while the
  heavy files go;
* **the janitor** - a sweep of the artifact and upload directories: a file no
  row refers to is deleted (a cancelled run, a crashed write), a row whose
  file is missing is marked, so the run view can say so instead of failing
  at predict time with a FileNotFoundError.

Everything here is dialect-neutral SQL and plain filesystem work; the caller
owns the transaction.
"""

from datetime import datetime, timedelta, timezone
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Dataset, Deployment, QuotaProfile, TrainingRun, User, UserQuotaOverride

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def remove_artifact_files(artifact_path: str) -> bool:
    """Remove an artifact of either format (a bundle directory or a file)."""
    if not artifact_path:
        return False
    path = Path(artifact_path)
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            return True
        if path.exists():
            path.unlink()
            return True
    except OSError:
        logger.warning("The artifact %s could not be removed", artifact_path)
    return False


async def run_is_served_by_deployment(db: AsyncSession, run_id: int) -> Optional[str]:
    """The name of the deployment that serves this run, if any."""
    result = await db.execute(
        select(Deployment.name).where(Deployment.run_id == run_id).limit(1)
    )
    return result.scalars().first()


async def delete_run(db: AsyncSession, run: TrainingRun) -> Dict[str, Any]:
    """Delete one run: the row, the artifact, the charts.

    The charts and the metrics live in the row, so they die with it - that is
    what a delete means. The caller has already checked the state (a queued
    or running run is refused) and the deployments.
    """
    removed = remove_artifact_files(run.artifact_path or "")
    await db.delete(run)
    return {"id": run.id, "artifact_removed": removed}


async def apply_retention(db: AsyncSession) -> List[Dict[str, Any]]:
    """Drop the artifacts that the profiles' retention rules retired.

    For every user whose effective rule keeps fewer runs (or fewer days) than
    they hold: the artifacts of the oldest runs beyond the rule are removed,
    the runs keep their metrics and get ``artifact_removed_at``. A run that a
    deployment serves is skipped - dropping its file would break the predict
    that somebody paid for.
    """
    # Every (user, keep_runs, keep_days) that applies. The overrides come
    # from their rows; the profiles from the users' profile ids.
    rules: Dict[int, Dict[str, Optional[int]]] = {}

    profiles = (await db.execute(select(QuotaProfile))).scalars().all()
    overrides = (await db.execute(select(UserQuotaOverride))).scalars().all()
    users = (await db.execute(select(User.id, User.quota_profile_id))).all()

    default_profile = next((p for p in profiles if p.name == "free"), None)

    def _resolve(user_id: int, profile_id: Optional[int]) -> Dict[str, Optional[int]]:
        override = next((o for o in overrides if o.user_id == user_id), None)
        profile = next((p for p in profiles if p.id == profile_id), default_profile)
        resolved = {}
        for column in ("artifact_keep_runs", "artifact_keep_days"):
            value = getattr(override, column, None) if override is not None else None
            if value is None and profile is not None:
                value = getattr(profile, column, None)
            resolved[column] = value
        return resolved

    for user_id, profile_id in users:
        rule = _resolve(user_id, profile_id)
        if rule["artifact_keep_runs"] is not None or rule["artifact_keep_days"] is not None:
            rules[user_id] = rule

    if not rules:
        return []

    summary: List[Dict[str, Any]] = []
    for user_id, rule in rules.items():
        keep_runs = rule["artifact_keep_runs"]
        keep_days = rule["artifact_keep_days"]

        finished = (
            await db.execute(
                select(TrainingRun)
                .where(
                    TrainingRun.owner_id == user_id,
                    TrainingRun.artifact_path.isnot(None),
                    TrainingRun.artifact_removed_at.is_(None),
                    TrainingRun.status.in_(("completed", "failed", "cancelled")),
                )
                .order_by(TrainingRun.created_at.desc())
            )
        ).scalars().all()

        cutoff = _now() - timedelta(days=keep_days) if keep_days is not None else None
        doomed: List[TrainingRun] = []
        for position, run in enumerate(finished):
            # The newest keep_runs runs stay; everything older than keep_days
            # days goes. A run that fails either rule is a candidate.
            out_of_count = keep_runs is not None and position >= keep_runs
            too_old = cutoff is not None and run.created_at is not None and run.created_at.replace(
                tzinfo=timezone.utc if run.created_at.tzinfo is None else run.created_at.tzinfo
            ) < cutoff
            if out_of_count or too_old:
                doomed.append(run)

        for run in doomed:
            if await run_is_served_by_deployment(db, run.id):
                continue
            remove_artifact_files(run.artifact_path or "")
            await db.execute(
                update(TrainingRun)
                .where(TrainingRun.id == run.id)
                .values(
                    artifact_path=None,
                    artifact_sha256=None,
                    artifact_bytes=None,
                    artifact_removed_at=_now(),
                )
            )
        if doomed:
            summary.append({"user_id": user_id, "removed": len(doomed)})
    return summary


async def janitor_sweep(db: AsyncSession) -> Dict[str, Any]:
    """Reconcile the files on the disk with the rows in the database.

    * a file in the models or uploads tree that no row refers to is removed
      (a cancelled run, a crash between the write and the commit);
    * a finished run whose artifact file is gone is marked, so the run view
      says ``artifact_removed`` instead of failing at predict time.
    """
    from .settings import datasets_root
    from .model_training import MODEL_DIR

    summary = {"orphaned_files": 0, "marked_missing": 0}

    # --- the files nobody refers to -------------------------------------
    run_paths: set = set()
    for (value,) in await db.execute(
        select(TrainingRun.artifact_path).where(TrainingRun.artifact_path.isnot(None))
    ):
        if value:
            run_paths.add(str(Path(value).resolve()))
    dataset_paths: set = set()
    for value in (
        await db.execute(select(Dataset.storage_path).where(Dataset.storage_path.isnot(None)))
    ).scalars():
        if value:
            try:
                from .datasets import resolve_storage_path

                dataset_paths.add(str(resolve_storage_path(value).resolve()))
            except Exception:  # noqa: BLE001 - an unresolvable row is not a file problem
                continue

    for tree, referenced in (
        (Path(MODEL_DIR), run_paths),
        (datasets_root() / "uploads", dataset_paths),
    ):
        if not tree.exists():
            continue
        for path in tree.rglob("*"):
            if not path.is_file():
                continue
            resolved = str(path.resolve())
            if resolved in referenced:
                continue
            try:
                path.unlink()
                summary["orphaned_files"] += 1
            except OSError:
                continue

    # --- the rows whose file is gone -------------------------------------
    missing = (
        await db.execute(
            select(TrainingRun).where(
                TrainingRun.artifact_path.isnot(None),
                TrainingRun.artifact_removed_at.is_(None),
            )
        )
    ).scalars().all()
    for run in missing:
        if not Path(run.artifact_path).exists():
            await db.execute(
                update(TrainingRun)
                .where(TrainingRun.id == run.id)
                .values(artifact_removed_at=_now())
            )
            summary["marked_missing"] += 1
    return summary
