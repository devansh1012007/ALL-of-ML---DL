"""The rate limiter, in the database (plan A8).

A limiter that lives in the memory of a process is a lie the moment a second
worker starts: every process has its own budget, and an attacker behind two
alternating addresses gets two budgets. The events live in the database now,
so every worker of the deployment shares one budget per key.

The window is a sliding one, counted in SQL: the events of a key that are
younger than the window. An attempt that falls out of the window frees the
budget, and a purge in the maintenance loop keeps the table itself small.

The keys name the thing that is limited:

* ``login:<address>`` and ``login:<address>:<account>`` - a failed login is
  counted under both, so one client cannot spray one password over many
  accounts and cannot hammer one account either;
* ``register:<address>``;
* ``upload:user:<id>`` and ``upload:addr:<address>`` - the authenticated
  caller is the budget that matters, the address budget is the second line
  against a compromised account on a rented machine;
* ``predict:user:<id>`` - the prediction endpoints count per user (the quota
  of plan A4 holds the numbers; this table is the ledger they are counted
  in when a quota does not).

The functions take the session and commit nothing: the caller owns the
transaction, because a rate check is usually one query inside a request that
has more to do.
"""

from datetime import datetime, timedelta, timezone
import os
import random
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RateEvent

# The window every limit is counted in. A fixed short window is enough here:
# the limits exist to stop a password spray and an upload flood, not to
# meter a paying customer.
RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# How often the maintenance purge may run, and how old a row may get before
# it is worth deleting. The purge is also triggered lazily (a small chance on
# every insert) so a deployment without the loop still does not fill the disk.
RATE_LIMIT_PURGE_AFTER_SECONDS = max(RATE_LIMIT_WINDOW_SECONDS * 2, 300)

# The lazy purge runs on roughly one insert in fifty: it costs a DELETE over
# a small indexed range and keeps the table bounded even when the maintenance
# loop is not running.
_LAZY_PURGE_CHANCE = 0.02


class RateLimitExceeded(Exception):
    """The key used up its budget. The endpoint answers 429."""

    def __init__(self, detail: str = "Too many attempts. Please try again in a minute."):
        super().__init__(detail)
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def count_events(db: AsyncSession, key: str, window_seconds: float) -> int:
    """How many events the key has in the sliding window."""
    since = _now() - timedelta(seconds=window_seconds)
    result = await db.execute(
        select(func.count())
        .select_from(RateEvent)
        .where(RateEvent.key == key, RateEvent.at > since)
    )
    return int(result.scalar_one())


async def check_rate_limit(db: AsyncSession, key: str, limit: int) -> None:
    """Raise :class:`RateLimitExceeded` when the key used up its budget.

    A limit of zero or less turns the check off, which is how a deployment
    disables one limit without touching the code.
    """
    if limit <= 0:
        return
    used = await count_events(db, key, RATE_LIMIT_WINDOW_SECONDS)
    if used >= limit:
        raise RateLimitExceeded()


async def record_rate_limit(db: AsyncSession, key: str) -> None:
    """Count one attempt against the key's budget."""
    db.add(RateEvent(key=key, at=_now()))
    await db.flush()
    if random.random() < _LAZY_PURGE_CHANCE:
        await purge_rate_events(db)


async def forget_rate_limit(db: AsyncSession, key: str) -> None:
    """Give the key its budget back after a successful attempt.

    Only a *failed* login counts, so a user who signs in and out repeatedly
    never locks themselves out.
    """
    await db.execute(delete(RateEvent).where(RateEvent.key == key))


async def purge_rate_events(db: AsyncSession, older_than_seconds: Optional[float] = None) -> int:
    """Delete the events that fell out of every window. Returns the count."""
    horizon = _now() - timedelta(
        seconds=older_than_seconds if older_than_seconds is not None else RATE_LIMIT_PURGE_AFTER_SECONDS
    )
    result = await db.execute(delete(RateEvent).where(RateEvent.at < horizon))
    return result.rowcount or 0


async def reset_rate_limits(db: AsyncSession) -> None:
    """Forget every recorded attempt.

    The test suite uses it so that every test starts with a clean budget.
    """
    await db.execute(delete(RateEvent))


def purge_rate_events_on_engine(older_than_seconds: Optional[float] = None) -> None:
    """A synchronous purge against the configured database.

    The maintenance loop and the endpoints run inside the event loop of the
    process and use :func:`purge_rate_events`; callers that live outside that
    loop (a test, a cron script) use this one. The engine is created and
    disposed inside one ``asyncio.run``, so no connection is left bound to a
    dead loop.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from .settings import DATABASE_URL

    async def _purge():
        engine = create_async_engine(DATABASE_URL)
        factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                await purge_rate_events(session, older_than_seconds)
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_purge())
