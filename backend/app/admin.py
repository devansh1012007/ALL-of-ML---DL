"""The admin API: identity, quotas, the queue and the audit log (plans A1, A6, A9).

Why this module exists
----------------------
An admin who can only list users cannot do the job. This module gives the
admin screen everything it needs - the users with their status and profile,
the usage of every account, the queue with a cancel button, the invites, the
quota profiles and the audit trail - behind one role check that is attached
to every route when the router is included, so an admin route can never be
exposed without it.

The registration mode (plan A1) lives here as well: "open" (today's
behaviour), "approval" (an account waits for an admin), "invite" (a one-time
code an admin created). And the first admin is created by a command or by
the bootstrap environment pair - never by editing the database by hand.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import getpass
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import hash_pass
from .database import get_db
from .models import (
    ApiKey,
    AuditEvent,
    Dataset,
    Deployment,
    Invite,
    QuotaProfile,
    TrainingRun,
    User,
    UserQuotaOverride,
)
from .quotas import QUOTA_COLUMNS, effective_quota, seed_quota_profiles, user_usage

# The registration mode of the deployment (plan A1): "open" (anyone may
# register, the account is active at once), "approval" (the account waits as
# "pending" until an admin approves it) or "invite" (registration needs a
# one-time code an admin created).
REGISTRATION_MODE = os.getenv("REGISTRATION_MODE", "open").strip().lower()
if REGISTRATION_MODE not in ("open", "approval", "invite"):
    raise RuntimeError(
        f"REGISTRATION_MODE must be one of open, approval, invite; "
        f"got {REGISTRATION_MODE!r}."
    )

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def audit(
    db: AsyncSession,
    actor_id: Optional[int],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[Any] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Write an audit event (plan A9).

    Called on every privileged change: role and status changes, quota edits,
    deletions, admin cancels, invites. The write is its own commit so the
    event survives even when the caller rolls back afterwards.
    """
    db.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            detail=detail or {},
        )
    )
    await db.commit()


def _actor(request: Request) -> Optional[int]:
    """The admin who made the request (set by the guard main.py attaches)."""
    actor = getattr(request.state, "admin_user", None)
    return actor.id if actor is not None else None


# --- the request bodies --------------------------------------------------------


class UserPatch(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    quota_profile_id: Optional[int] = None
    email: Optional[str] = None
    # The per-user overrides of plan A3: only the sent keys change.
    overrides: Optional[Dict[str, Any]] = None


class QuotaProfilePut(BaseModel):
    values: Dict[str, Any] = Field(default_factory=dict)


class InviteCreate(BaseModel):
    max_uses: int = Field(1, ge=1, le=1000)
    expires_days: int = Field(7, ge=1, le=365)


# --- the users -----------------------------------------------------------------


def _user_dict(user: User, usage: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "status": getattr(user, "status", "active"),
        "email": getattr(user, "email", None),
        "quota_profile_id": getattr(user, "quota_profile_id", None),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": (
            user.last_login_at.isoformat() if getattr(user, "last_login_at", None) else None
        ),
        "usage": usage,
    }


@router.get("/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    profile: Optional[int] = None,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """The users, paginated, filterable by status and profile (plan A6)."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    query = select(User)
    if status_filter:
        query = query.where(User.status == status_filter)
    if profile is not None:
        query = query.where(User.quota_profile_id == profile)
    if q:
        query = query.where(User.username.ilike(f"%{q}%"))
    total = len((await db.execute(select(func.count()).select_from(query.subquery()))).all())
    users = (
        await db.execute(query.order_by(User.id).limit(limit).offset(offset))
    ).scalars().all()
    return {
        "items": [_user_dict(user) for user in users],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/users/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """One user with the usage panel of plan A7: a quota the user cannot see
    is experienced as a bug, and the admin needs the same numbers to answer."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    usage = await user_usage(db, user)
    quota = await effective_quota(db, user)
    return _user_dict(user, {**usage, "quota": quota})


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: int,
    body: UserPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Change the role, the status, the profile or the overrides of a user.

    Changing the role or the status increments ``token_version`` (plan A2),
    so the suspended user's existing token stops working at the next request
    - the row is re-read every time, the token never has to expire.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    actor_id = _actor(request)
    changes: Dict[str, Any] = {}

    if body.role is not None:
        if body.role not in ("user", "admin"):
            raise HTTPException(status_code=422, detail="role must be 'user' or 'admin'.")
        if user.role == "admin" and body.role != "admin":
            # Demoting the last admin locks everybody out (plan A6): the
            # lock-out would need a database edit to undo.
            admins = (
                await db.execute(select(func.count(User.id)).where(User.role == "admin"))
            ).scalar() or 0
            if admins <= 1:
                raise HTTPException(
                    status_code=409, detail="The last admin cannot be demoted."
                )
        changes["role"] = body.role
        user.role = body.role
        user.token_version = (user.token_version or 0) + 1

    if body.status is not None:
        if body.status not in ("pending", "active", "suspended"):
            raise HTTPException(
                status_code=422,
                detail="status must be one of pending, active, suspended.",
            )
        changes["status"] = body.status
        user.status = body.status
        user.token_version = (user.token_version or 0) + 1

    if body.quota_profile_id is not None:
        profile = await db.get(QuotaProfile, body.quota_profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Quota profile not found")
        changes["quota_profile_id"] = body.quota_profile_id
        user.quota_profile_id = body.quota_profile_id

    if body.email is not None:
        changes["email"] = body.email
        user.email = body.email

    if body.overrides is not None:
        unknown = sorted(set(body.overrides) - set(QUOTA_COLUMNS))
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown quota override(s): {unknown}",
            )
        override = (
            await db.execute(
                select(UserQuotaOverride).where(UserQuotaOverride.user_id == user.id)
            )
        ).scalars().first()
        if override is None:
            override = UserQuotaOverride(user_id=user.id)
            db.add(override)
        for key, value in body.overrides.items():
            setattr(override, key, value)
        changes["overrides"] = body.overrides

    await db.commit()
    if changes:
        await audit(
            db, actor_id, "admin.user.patched", "user", user.id, {"changes": changes}
        )
    return _user_dict(user)


@router.post("/users/{user_id}/approve")
async def approve_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Activate a pending account (plan A1)."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != "pending":
        raise HTTPException(status_code=409, detail=f"The user is {user.status}, not pending.")
    user.status = "active"
    await db.commit()
    await audit(
        db,
        _actor(request),
        "admin.user.approved",
        "user",
        user.id,
    )
    return _user_dict(user)


@router.post("/users/{user_id}/suspend")
async def suspend_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Suspend an account: the login is refused and the tokens stop working
    at the next request (plan A1). Reversible, where deletion is not."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        admins = (
            await db.execute(select(func.count(User.id)).where(User.role == "admin"))
        ).scalar() or 0
        if admins <= 1:
            raise HTTPException(
                status_code=409, detail="The last admin cannot be suspended."
            )
    user.status = "suspended"
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    await audit(
        db,
        _actor(request),
        "admin.user.suspended",
        "user",
        user.id,
    )
    return _user_dict(user)


async def purge_user(db: AsyncSession, user: User) -> int:
    """Delete a user with their runs, datasets and files (plan A1/A6/H1).

    Shared by the admin route and the self-service deletion: the runs cascade
    with the row, the files are removed first (the rows are the registry),
    and the sessions, the API keys and the deployments of the account go
    through their own deletes. Returns the number of files removed.
    """
    from .cleanup import remove_artifact_files
    from .datasets import resolve_storage_path, DatasetError
    from .models import RefreshToken

    removed_files = 0
    runs = (
        await db.execute(select(TrainingRun).where(TrainingRun.owner_id == user.id))
    ).scalars().all()
    for run in runs:
        if run.artifact_path and remove_artifact_files(run.artifact_path):
            removed_files += 1
    datasets = (
        await db.execute(select(Dataset).where(Dataset.owner_id == user.id))
    ).scalars().all()
    for dataset in datasets:
        try:
            path = resolve_storage_path(dataset.storage_path)
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed_files += 1
            elif path.exists():
                path.unlink()
                removed_files += 1
        except (DatasetError, OSError):
            pass
        # The rows are deleted here and not by the cascade: the datasets of a
        # user are related by the owner_id column only.
        await db.delete(dataset)

    # Everything that names the user outside the cascade: the sessions of
    # plan A2, the predict keys and the deployments of plan D.
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await db.execute(delete(ApiKey).where(ApiKey.user_id == user.id))
    await db.execute(delete(Deployment).where(Deployment.owner_id == user.id))

    await db.delete(user)  # the runs and the datasets cascade
    return removed_files


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete a user with their runs, datasets and files (plan A6).

    Refuses to delete the last admin: a lock-out that would need a database
    edit to undo is worse than refusing the click.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        admins = (
            await db.execute(select(func.count(User.id)).where(User.role == "admin"))
        ).scalar() or 0
        if admins <= 1:
            raise HTTPException(
                status_code=409, detail="The last admin cannot be deleted."
            )

    removed_files = await purge_user(db, user)
    await db.commit()
    await audit(
        db,
        _actor(request),
        "admin.user.deleted",
        "user",
        user.id,
        {"files_removed": removed_files},
    )
    return {"id": user_id, "deleted": True, "files_removed": removed_files}


# --- the usage and the profiles -------------------------------------------------


@router.get("/usage")
async def admin_usage(db: AsyncSession = Depends(get_db)):
    """The usage of every account (plan A6): runs today, CPU seconds this
    month, storage, and whether each is near its limit."""
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    items = []
    for user in users:
        usage = await user_usage(db, user)
        near: List[str] = []
        limits = usage["limits"]
        if limits["max_runs_per_day"] and usage["runs_today"] >= 0.8 * limits["max_runs_per_day"]:
            near.append("max_runs_per_day")
        if limits["max_storage_bytes"] and usage["storage_bytes"] >= 0.8 * limits["max_storage_bytes"]:
            near.append("max_storage_bytes")
        if (
            limits["max_cpu_seconds_per_month"]
            and usage["cpu_seconds_this_month"] >= 0.8 * limits["max_cpu_seconds_per_month"]
        ):
            near.append("max_cpu_seconds_per_month")
        items.append(
            {
                "user_id": user.id,
                "username": user.username,
                **usage,
                "near_limits": near,
            }
        )
    return {"items": items}


@router.get("/quota-profiles")
async def list_quota_profiles(db: AsyncSession = Depends(get_db)):
    profiles = (await db.execute(select(QuotaProfile).order_by(QuotaProfile.id))).scalars().all()
    return {
        "items": [{c.name: getattr(p, c.name) for c in p.__table__.columns} for p in profiles]
    }


@router.put("/quota-profiles/{profile_id}")
async def put_quota_profile(
    profile_id: int,
    body: QuotaProfilePut,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Edit the limits of a profile (plan A6): the values are data, the
    columns that are not sent keep theirs, and a null means unlimited."""
    profile = await db.get(QuotaProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Quota profile not found")
    unknown = sorted(set(body.values) - set(QUOTA_COLUMNS) - {"name"})
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown quota column(s): {unknown}")
    for key, value in body.values.items():
        setattr(profile, key, value)
    await db.commit()
    await audit(
        db,
        _actor(request),
        "admin.quota_profile.edited",
        "quota_profile",
        profile_id,
        {"changes": body.values},
    )
    return {c.name: getattr(profile, c.name) for c in profile.__table__.columns}


# --- the queue -------------------------------------------------------------------


@router.get("/queue")
async def admin_queue(db: AsyncSession = Depends(get_db)):
    """Every queued and running run with its owner (plan A6): what the
    machine is doing, answerable without a database shell."""
    runs = (
        await db.execute(
            select(TrainingRun, User.username)
            .join(User, TrainingRun.owner_id == User.id)
            .where(TrainingRun.status.in_(["queued", "running"]))
            .order_by(TrainingRun.status, TrainingRun.id)
        )
    ).all()
    return {
        "items": [
            {
                "id": run.id,
                "owner": username,
                "owner_id": run.owner_id,
                "model_name": run.model_name,
                "job_kind": run.job_kind,
                "status": run.status,
                "dataset_tag": run.dataset_tag,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
            }
            for run, username in runs
        ]
    }


@router.post("/queue/{run_id}/cancel")
async def admin_cancel_run(run_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Cancel any run, not only the caller's own (plan A6)."""
    from .main import cancel_run_row, STATUS_QUEUED, STATUS_RUNNING

    run = await db.get(TrainingRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    if run.status not in (STATUS_QUEUED, STATUS_RUNNING):
        raise HTTPException(status_code=409, detail=f"The run is already {run.status}.")
    cancelled = await cancel_run_row(db, run)
    if cancelled:
        await audit(
            db,
            _actor(request),
            "admin.run.cancelled",
            "run",
            run_id,
            {"owner_id": run.owner_id, "model": run.model_name},
        )
    return {"id": run_id, "cancelled": bool(cancelled)}


# --- the invites (plan A1) --------------------------------------------------------


@router.post("/invites")
async def create_invite(
    body: InviteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a one-time registration code (plan A1, mode "invite").

    The code is shown once, stored hashed, expires, and is counted: the same
    code can serve a class of twenty with ``max_uses``.
    """
    code = secrets.token_urlsafe(12)
    invite = Invite(
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        created_by=_actor(request),
        max_uses=body.max_uses,
        expires_at=_now() + timedelta(days=body.expires_days),
    )
    db.add(invite)
    await db.commit()
    await audit(
        db,
        _actor(request),
        "admin.invite.created",
        "invite",
        invite.id,
        {"max_uses": body.max_uses, "expires_days": body.expires_days},
    )
    return {"id": invite.id, "code": code, "max_uses": invite.max_uses, "expires_at": invite.expires_at.isoformat()}


@router.get("/invites")
async def list_invites(db: AsyncSession = Depends(get_db)):
    invites = (
        await db.execute(select(Invite).order_by(Invite.id.desc()).limit(200))
    ).scalars().all()
    now = _now()

    def _aware(value):
        # SQLite returns naive datetimes; the comparison needs one time zone.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    return {
        "items": [
            {
                "id": invite.id,
                "max_uses": invite.max_uses,
                "use_count": invite.use_count,
                "expires_at": invite.expires_at.isoformat(),
                "expired": _aware(invite.expires_at) < now,
                "exhausted": invite.use_count >= invite.max_uses,
                "created_at": invite.created_at.isoformat() if invite.created_at else None,
            }
            for invite in invites
        ]
    }


# --- the audit log (plan A9) -------------------------------------------------------


@router.get("/audit")
async def read_audit(
    limit: int = 100,
    offset: int = 0,
    action: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """The audit events, newest first (plan A9)."""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    query = select(AuditEvent).order_by(AuditEvent.id.desc())
    if action:
        query = query.where(AuditEvent.action.ilike(f"%{action}%"))
    events = (await db.execute(query.limit(limit).offset(offset))).scalars().all()
    return {
        "items": [
            {
                "id": event.id,
                "actor_id": event.actor_id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "detail": event.detail,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
        "limit": limit,
        "offset": offset,
    }


# --- the first admin (plan A1) ------------------------------------------------------


async def bootstrap_admin(db: AsyncSession) -> Optional[User]:
    """Create the first admin from the environment pair, when none exists.

    ``BOOTSTRAP_ADMIN_USERNAME`` and ``BOOTSTRAP_ADMIN_PASSWORD`` create an
    admin only when no admin exists, so the pair cannot be used to add a
    second one. The alternative is the ``create-admin`` command below; the
    manual database edit is gone either way.
    """
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username or not password:
        return None
    admins = (
        await db.execute(select(func.count(User.id)).where(User.role == "admin"))
    ).scalar() or 0
    if admins:
        return None
    existing = (
        await db.execute(select(User).where(User.username == username))
    ).scalars().first()
    if existing is not None:
        return None
    user = User(
        username=username,
        hashed_password=hash_pass(password[:72]),
        role="admin",
        status="active",
    )
    db.add(user)
    await db.commit()
    return user


async def ensure_admin_and_profiles() -> None:
    """The startup seeding: the quota profiles and the first admin."""
    from .database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await seed_quota_profiles(session)
        # The admins get the unlimited profile (plan A3): the absence of
        # numbers, not a copy of every limit with a bigger value.
        unlimited = (
            await session.execute(
                select(QuotaProfile).where(QuotaProfile.name == "unlimited")
            )
        ).scalars().first()
        admin = await bootstrap_admin(session)
        if unlimited is not None:
            await session.execute(
                update(User)
                .where(User.role == "admin", User.quota_profile_id.is_(None))
                .values(quota_profile_id=unlimited.id)
            )
            await session.commit()


def create_admin_command(argv: List[str]) -> int:
    """``python -m backend.app.admin create-admin <username>`` (plan A1).

    Prompts for the password (never a command-line argument, which the shell
    history keeps), hashes it, and writes the row. Exits non-zero when the
    username is taken or the password is empty.
    """
    if len(argv) != 2 or argv[0] != "create-admin":
        print("usage: python -m backend.app.admin create-admin <username>", file=sys.stderr)
        return 2
    username = argv[1]
    password = getpass.getpass(f"Password for the admin '{username}': ")
    if not password:
        print("The password is empty; nothing was created.", file=sys.stderr)
        return 1
    if len(password) < 8:
        print("The password must have at least 8 characters.", file=sys.stderr)
        return 1

    from .database import AsyncSessionLocal
    from .auth import validate_credentials

    reason = validate_credentials(username, password)
    if reason:
        print(reason, file=sys.stderr)
        return 1

    async def _run() -> int:
        async with AsyncSessionLocal() as session:
            existing = (
                await session.execute(select(User).where(User.username == username))
            ).scalars().first()
            if existing is not None:
                print(f"The username '{username}' is already taken.", file=sys.stderr)
                return 1
            unlimited = (
                await session.execute(
                    select(QuotaProfile).where(QuotaProfile.name == "unlimited")
                )
            ).scalars().first()
            user = User(
                username=username,
                hashed_password=hash_pass(password[:72]),
                role="admin",
                status="active",
                quota_profile_id=unlimited.id if unlimited is not None else None,
            )
            session.add(user)
            await session.commit()
            await audit(session, user.id, "admin.created", "user", user.id, {"via": "command"})
            print(f"The admin '{username}' was created.")
            return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(create_admin_command(sys.argv[1:]))
