"""Browser sessions: the refresh token lifecycle (plan A2).

The access token is short (15 minutes by default) and cannot be taken back
except through ``token_version``, which ends *every* session of the account.
The session itself lives in a refresh token:

* it is issued at the login, travels to the browser in an httpOnly,
  ``SameSite=Strict`` cookie, and is stored **hashed** in the database - a
  stolen user table holds no usable session;
* refreshing **rotates** it: the presented token is marked revoked and the
  row names its replacement;
* presenting a token that was already rotated is the signature of a stolen
  family, so the whole family (every token that shares its ``family_id``) is
  revoked at once. The attacker's fresh copy dies with the victim's session;
* the logout revokes the presented token; the password change revokes every
  family of the account and bumps ``token_version``.

The raw token is returned by ``issue`` and never logged. The functions here
take the session explicitly and commit nothing themselves: the caller owns
the transaction, because the rotation is usually combined with other writes
(the login also stamps ``last_login_at``).
"""

from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RefreshToken

# The lifetime of a refresh token (plan A2: 7 days).
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))

# The cookie the refresh token travels in. The path is narrowed to the
# endpoints that consume it, so the browser stops sending it with every
# other request.
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def hash_token(raw: str) -> str:
    """The database form of a refresh token (sha256 hex).

    A refresh token is a 64-character random string, so a plain sha256 is
    enough: there is nothing to guess that a slower hash would slow down.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_aware(value: datetime) -> datetime:
    """A timestamp as the columns store it, read back in UTC.

    SQLite returns naive datetimes (the offset was stripped on the way in);
    the values were written as UTC, so a naive value *is* UTC. Without this,
    a comparison against a timezone-aware ``now`` raises on SQLite and works
    on Postgres - a dialect difference, not a behaviour.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def new_raw_token() -> str:
    return secrets.token_urlsafe(48)


async def issue_refresh_token(
    db: AsyncSession, user_id: int, family_id: Optional[str] = None
) -> Tuple[str, RefreshToken]:
    """Create a fresh refresh token for the user and return ``(raw, row)``.

    A new login starts a new family; a rotation passes the family of the
    token it replaces.
    """
    raw = new_raw_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(raw),
        family_id=family_id or secrets.token_hex(16),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
    )
    db.add(row)
    await db.flush()
    return raw, row


async def rotate_refresh_token(
    db: AsyncSession, raw: str
) -> Tuple[str, RefreshToken, RefreshToken]:
    """Rotate the presented token and return ``(new_raw, new_row, old_row)``.

    Raises ``SessionError`` when the token is unknown, expired or - the
    interesting case - already rotated. A reuse revokes every token of the
    family before the error is raised: the damage is contained even though
    the request fails.
    """
    presented = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
    ).scalars().first()
    if presented is None:
        raise SessionError("The session is no longer valid.")
    now = datetime.now(timezone.utc)
    if presented.revoked_at is not None or _as_aware(presented.expires_at) < now:
        # Reuse of a rotated token (or a replay of an expired one): the
        # family is compromised, so everything in it dies now.
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == presented.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        raise SessionError("The session is no longer valid.")
    new_raw, new_row = await issue_refresh_token(db, presented.user_id, presented.family_id)
    presented.revoked_at = now
    presented.replaced_by = new_row.id
    return new_raw, new_row, presented


async def revoke_refresh_token(db: AsyncSession, raw: str) -> bool:
    """Revoke one token (the logout). ``False`` when it was already dead."""
    row = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
    ).scalars().first()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    return True


async def revoke_all_for_user(db: AsyncSession, user_id: int) -> int:
    """Revoke every live session of the account (the password change)."""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    return result.rowcount or 0


class SessionError(Exception):
    """The presented refresh token is unusable (unknown, expired or reused)."""
