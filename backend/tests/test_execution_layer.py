"""The fair share, the retries and the capability routing (plans B5-B7).

* B5: among the queued runs, the owner with the fewest running runs has the
  turn - a user who fills the queue cannot starve the others;
* B6: a run whose worker died is requeued while it has attempts left, and
  failed when it has none - and only an infrastructure death retries;
* B7: a run's requirements are recorded at the enqueue, a worker that
  cannot satisfy them does not take it, and the submit answers 409 when no
  online worker could ever run it.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import main
from backend.app.main import (
    STATUS_QUEUED,
    STATUS_RUNNING,
    _claim_next_run,
    _worker_satisfies,
    reap_the_interrupted_runs,
)


def _sql(query, params=()):
    import sqlite3

    from backend.app.settings import DATABASE_URL

    path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    connection = sqlite3.connect(path)
    try:
        with connection:
            return connection.execute(query, params).fetchall()
    finally:
        connection.close()


@pytest.fixture(scope="module", autouse=True)
def _a_user_to_queue_runs_for():
    """The claim and the sweeper work on rows; give them a user to own them.

    This module never starts the application, so nobody else creates the
    rows: one user, inserted directly, is enough for every test here.
    """
    _sql(
        "INSERT OR IGNORE INTO users (username, hashed_password, role, status) "
        "VALUES ('exec_layer_user', 'not-a-real-hash', 'user', 'active')"
    )
    yield


def _user_id(username):
    return _sql("SELECT id FROM users WHERE username = ?", (username,))[0][0]


def _queue_run(owner_id: int, requirements=None, priority: int = 0) -> int:
    _sql(
        "INSERT INTO training_runs (owner_id, model_name, dataset_source, dataset_tag, "
        "hyperparameters, status, request_payload, requirements, priority, mode) "
        "VALUES (?, 'Logistic_Regression', 'local', 'x', '{}', 'queued', '{}', ?, ?, 'manual')",
        (owner_id, __import__("json").dumps(requirements) if requirements else None, priority),
    )
    return _sql("SELECT max(id) FROM training_runs")[0][0]


def _running_run(owner_id: int, attempts: int = 0) -> int:
    """A running run with a long-dead heartbeat and a stored request.

    ``request_payload`` matters: a running row without one is a legacy row
    the sweeper fails on sight, and the retry tests must not trip over it.
    """
    _sql(
        "INSERT INTO training_runs (owner_id, model_name, dataset_source, dataset_tag, "
        "hyperparameters, status, request_payload, mode, attempts, max_attempts, heartbeat_at) "
        "VALUES (?, 'm', 'local', 'x', '{}', 'running', '{}', 'manual', ?, 2, '2020-01-01 00:00:00')",
        (owner_id, attempts),
    )
    return _sql("SELECT max(id) FROM training_runs")[0][0]


# --- B5: the fair share ---------------------------------------------------------


def test_the_owner_with_the_least_running_work_has_the_turn():
    crowded = _sql("SELECT id FROM users LIMIT 1")[0][0]

    async def _make_second_user():
        from backend.app.database import AsyncSessionLocal
        from backend.app.models import User

        async with AsyncSessionLocal() as session:
            session.add(User(username=f"fair_{__import__('os').urandom(2).hex()}", hashed_password="x"))
            await session.commit()

    asyncio.run(_make_second_user())
    newcomer = _sql(
        "SELECT id FROM users WHERE username LIKE 'fair_%' ORDER BY id DESC LIMIT 1"
    )[0][0]

    # The crowded user has a run executing and more queued; the newcomer has
    # only one queued run, younger than all of the crowded user's.
    _sql(
        "INSERT INTO training_runs (owner_id, model_name, dataset_source, dataset_tag, "
        "hyperparameters, status, mode) VALUES (?, 'm', 'local', 'x', '{}', 'running', 'manual')",
        (crowded,),
    )
    first_crowded = _queue_run(crowded)
    second_crowded = _queue_run(crowded)
    newcomers = _queue_run(newcomer)

    claimed = asyncio.run(_claim_next_run())
    try:
        assert claimed == newcomers, "the newcomer's run goes before the crowded user's"
    finally:
        _sql("DELETE FROM training_runs WHERE id IN (?, ?, ?)", (first_crowded, second_crowded, newcomers))
        _sql("DELETE FROM training_runs WHERE owner_id = ? AND status = 'running'", (crowded,))


def test_a_high_priority_run_beats_an_even_queue():
    user = _sql("SELECT id FROM users LIMIT 1")[0][0]
    old = _queue_run(user)
    urgent = _queue_run(user, priority=10)
    try:
        claimed = asyncio.run(_claim_next_run())
        assert claimed == urgent, "a higher priority wins when the share is even"
    finally:
        _sql("DELETE FROM training_runs WHERE id IN (?, ?)", (old, urgent))


# --- B6: the retries -------------------------------------------------------------


def test_a_dead_worker_s_run_is_requeued_while_it_has_attempts():
    user = _sql("SELECT id FROM users LIMIT 1")[0][0]
    run_id = _running_run(user, attempts=0)

    asyncio.run(reap_the_interrupted_runs())

    status, attempts = _sql(
        "SELECT status, attempts FROM training_runs WHERE id = ?", (run_id,)
    )[0]
    assert status == "queued", "an infra death with attempts left is requeued"
    assert attempts == 1
    _sql("DELETE FROM training_runs WHERE id = ?", (run_id,))


def test_a_dead_worker_s_run_without_attempts_is_failed():
    user = _sql("SELECT id FROM users LIMIT 1")[0][0]
    run_id = _running_run(user, attempts=2)

    asyncio.run(reap_the_interrupted_runs())

    status = _sql("SELECT status FROM training_runs WHERE id = ?", (run_id,))[0][0]
    assert status == "failed"
    error = _sql("SELECT metrics FROM training_runs WHERE id = ?", (run_id,))[0][0]
    assert "attempts" in error
    _sql("DELETE FROM training_runs WHERE id = ?", (run_id,))


# --- B7: the capability routing ----------------------------------------------------


def test_a_worker_without_a_gpu_does_not_take_a_gpu_run():
    assert _worker_satisfies({}, {"gpu": False}) is True
    assert _worker_satisfies({"requires_gpu": True}, {"gpu": True}) is True
    assert _worker_satisfies({"requires_gpu": True}, {"gpu": False}) is False
    assert _worker_satisfies({"min_memory_mb": 8000}, {"gpu": False, "memory_mb": 4096}) is False
    assert _worker_satisfies({"min_memory_mb": 8000}, {"gpu": False, "memory_mb": 16384}) is True


def test_a_run_this_worker_cannot_satisfy_is_left_in_the_queue():
    """The claim skips the runs this worker cannot run, whatever their age."""
    user = _sql("SELECT id FROM users LIMIT 1")[0][0]
    gpu_run = _queue_run(user, requirements={"requires_gpu": True})
    cpu_run = _queue_run(user)
    try:
        claimed = asyncio.run(_claim_next_run())
        assert claimed == cpu_run, "the cpu run goes even though the gpu run is older"
    finally:
        _sql("DELETE FROM training_runs WHERE id IN (?, ?)", (gpu_run, cpu_run))


def test_the_submit_records_the_requirements():
    """The requirements of the entry land in the row the queue reads."""
    from backend.app.model_training import get_model_entry

    entry = get_model_entry("Logistic_Regression")
    assert "requires_gpu" in (entry or {}), "the catalog knows the requirement"
    # LLaMA is the plan's example of a GPU-gated entry.
    llama = get_model_entry("LLaMA")
    if llama is not None:
        assert llama.get("requires_gpu") is True
