"""The training queue: the rows of ``training_runs`` are the queue.

The previous version kept a run in the memory of the process that started it.
That has three consequences these tests pin down in their replacement:

* a queued run survives a restart (the request is stored in the row) and is
  claimed by whichever process asks first, exactly once;
* a worker says that it is alive while it trains, and the sweeper fails only
  the runs whose heartbeat stopped - it never fails the run of a live worker,
  which the old "fail every running row at startup" did;
* a run can be cancelled: a queued one never starts, a running one is marked
  at once and its result is discarded when it ends.

The tests drive the queue by hand (``TRAINING_IN_API`` is switched off, so a
request only enqueues) and use a fake ``train_model`` where the timing matters.
"""

import asyncio
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from backend.app import main
from backend.app.database import DATABASE_URL
from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login(client, username):
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def auth(client):
    return _login(client, "queue_user")


@pytest.fixture(scope="module")
def other_auth(client):
    return _login(client, "queue_other_user")


@pytest.fixture(autouse=True)
def only_enqueue(monkeypatch):
    """A request enqueues and nothing else: the test decides when a worker runs."""
    monkeypatch.setattr(main, "TRAINING_IN_API", False)


def _enqueue(client, auth):
    listing = client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
    dataset = next(d for d in listing if d["name"] == "sample_customer_churn.csv")
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Logistic_Regression",
            "dataset_id": dataset["id"],
            "label_column": dataset["label_column"],
            "cv_folds": 0,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _run(client, auth, run_id):
    response = client.get(f"/api/v1/ml/runs/{run_id}", headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


def _sql(statement, *params):
    """Run a statement against the test database with the standard library."""
    connection = sqlite3.connect(make_url(DATABASE_URL).database)
    try:
        cursor = connection.execute(statement, params)
        connection.commit()
        return cursor.fetchall()
    finally:
        connection.close()


def _stamp(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _owner_id(username):
    return _sql("SELECT id FROM users WHERE username = ?", username)[0][0]


def _insert_run(owner_id, status, heartbeat=None, with_request=True):
    _sql(
        "INSERT INTO training_runs (owner_id, model_name, dataset_source, dataset_tag, "
        "hyperparameters, mode, status, heartbeat_at, request_payload) "
        "VALUES (?, 'Logistic_Regression', 'local', 'x.csv', '{}', 'manual', ?, ?, ?)",
        owner_id,
        status,
        _stamp(heartbeat) if heartbeat else None,
        '{"request": {"model_name": "Logistic_Regression"}}' if with_request else None,
    )
    return _sql("SELECT max(id) FROM training_runs")[0][0]


# --- the run is a queue entry -------------------------------------------------


def test_a_request_stores_what_a_worker_needs_and_leaves_the_run_queued(client, auth):
    run_id = _enqueue(client, auth)

    assert _run(client, auth, run_id)["status"] == "queued"
    stored = _sql("SELECT request_payload FROM training_runs WHERE id = ?", run_id)[0][0]
    assert "Logistic_Regression" in stored and "storage_path" in stored

    asyncio.run(main.drain_training_queue())  # leave nothing queued behind
    assert _run(client, auth, run_id)["status"] == "completed"


def test_a_queued_run_survives_a_restart_and_is_trained_by_the_next_worker(client, auth):
    """The worker has only the database: nothing of the request is in memory."""
    run_id = _enqueue(client, auth)
    assert _run(client, auth, run_id)["status"] == "queued"

    # A "new process": a fresh coroutine that knows nothing but the table.
    asyncio.run(main.drain_training_queue())

    run = _run(client, auth, run_id)
    assert run["status"] == "completed", run
    assert run["metrics"]["accuracy"] > 0.5
    assert run["artifact_path"]
    assert run["started_at"] and run["finished_at"]


def test_a_run_is_claimed_exactly_once_however_many_workers_ask(client, auth):
    run_id = _enqueue(client, auth)

    async def two_workers_ask():
        return await asyncio.gather(main._claim_next_run(), main._claim_next_run())

    claimed = asyncio.run(two_workers_ask())

    assert sorted(c for c in claimed if c is not None) == [run_id]
    row = _sql("SELECT status, worker_id FROM training_runs WHERE id = ?", run_id)[0]
    assert row == ("running", main.WORKER_ID)
    # Give the claimed run back to the queue and finish it.
    _sql("UPDATE training_runs SET status = 'queued' WHERE id = ?", run_id)
    asyncio.run(main.drain_training_queue())


def test_a_process_never_trains_more_runs_than_its_concurrency(client, auth, monkeypatch):
    monkeypatch.setattr(main, "TRAINING_CONCURRENCY", 1)
    first, second = _enqueue(client, auth), _enqueue(client, auth)
    active, peak = [0], [0]
    lock = threading.Lock()

    def slow_training(*args, **kwargs):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.2)
        with lock:
            active[0] -= 1
        # The artifact record of plan C1 (path, checksum, bytes).
        return (
            {"accuracy": 1.0},
            "local",
            "x.csv",
            {"artifact_path": "/nonexistent/artifact.joblib", "artifact_sha256": None, "artifact_bytes": 1},
        )

    monkeypatch.setattr(main, "train_model", slow_training)

    async def two_drains():
        await asyncio.gather(main.drain_training_queue(), main.drain_training_queue())

    asyncio.run(two_drains())

    assert peak[0] == 1
    assert {_run(client, auth, r)["status"] for r in (first, second)} == {"completed"}


# --- the heartbeat and the sweeper --------------------------------------------


def test_a_worker_says_that_it_is_alive_while_it_trains(client, auth, monkeypatch):
    monkeypatch.setattr(main, "TRAINING_HEARTBEAT_SECONDS", 0.05)
    run_id = _enqueue(client, auth)
    started, release = threading.Event(), threading.Event()

    def blocked_training(*args, **kwargs):
        started.set()
        release.wait(10)
        # The artifact record of plan C1 (path, checksum, bytes).
        return (
            {"accuracy": 1.0},
            "local",
            "x.csv",
            {"artifact_path": "/nonexistent/artifact.joblib", "artifact_sha256": None, "artifact_bytes": 1},
        )

    monkeypatch.setattr(main, "train_model", blocked_training)
    worker = threading.Thread(target=lambda: asyncio.run(main.drain_training_queue()))
    worker.start()
    try:
        assert started.wait(10)
        first = _run(client, auth, run_id)["heartbeat_at"]
        time.sleep(0.4)
        later = _run(client, auth, run_id)

        assert later["status"] == "running"
        assert first and later["heartbeat_at"] > first
    finally:
        release.set()
        worker.join(15)
    assert _run(client, auth, run_id)["status"] == "completed"


def test_the_sweeper_fails_a_dead_run_and_leaves_a_live_one_alone(client, auth):
    """Two runs are 'running'; only the one whose heartbeat stopped is failed.

    The previous version failed every running row at startup, which is wrong
    the moment a second process runs: it killed the runs of the first.
    """
    owner = _owner_id("queue_user")
    now = datetime.now(timezone.utc)
    dead = _insert_run(owner, "running", heartbeat=now - timedelta(seconds=600))
    never_beat = _insert_run(owner, "running", heartbeat=None)
    alive = _insert_run(owner, "running", heartbeat=now)
    orphan = _insert_run(owner, "queued", with_request=False)

    asyncio.run(main.reap_the_interrupted_runs())

    assert _run(client, auth, dead)["status"] == "failed"
    assert "restarted or crashed" in _run(client, auth, dead)["metrics"]["error"]
    assert _run(client, auth, never_beat)["status"] == "failed"
    assert _run(client, auth, alive)["status"] == "running"
    assert _run(client, auth, orphan)["status"] == "failed"
    assert "older version" in _run(client, auth, orphan)["metrics"]["error"]
    _sql("UPDATE training_runs SET status = 'failed' WHERE id = ?", alive)


# --- cancel ----------------------------------------------------------------------


def test_a_queued_run_that_is_cancelled_never_starts(client, auth):
    run_id = _enqueue(client, auth)

    response = client.post(f"/api/v1/ml/runs/{run_id}/cancel", headers=auth)

    assert response.status_code == 200, response.text
    assert response.json() == {"id": run_id, "status": "cancelled", "was": "queued"}
    asyncio.run(main.drain_training_queue())
    run = _run(client, auth, run_id)
    assert run["status"] == "cancelled"
    assert run["artifact_path"] is None
    assert run["metrics"]["cancelled"] is True


def test_a_running_run_is_marked_cancelled_and_its_result_is_discarded(
    client, auth, monkeypatch, tmp_path
):
    run_id = _enqueue(client, auth)
    started, release = threading.Event(), threading.Event()
    artifact = tmp_path / "models" / "orphan.joblib"
    artifact.parent.mkdir(exist_ok=True)

    def blocked_training(*args, **kwargs):
        started.set()
        release.wait(10)
        artifact.write_bytes(b"the artifact of a cancelled run")
        return (
            {"accuracy": 1.0},
            "local",
            "x.csv",
            {"artifact_path": str(artifact), "artifact_sha256": None, "artifact_bytes": artifact.stat().st_size},
        )

    monkeypatch.setattr(main, "train_model", blocked_training)
    worker = threading.Thread(target=lambda: asyncio.run(main.drain_training_queue()))
    worker.start()
    try:
        assert started.wait(10)
        response = client.post(f"/api/v1/ml/runs/{run_id}/cancel", headers=auth)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["was"] == "running"
        # The answer does not pretend that the training stopped.
        assert "cannot be interrupted" in body["note"]
        assert _run(client, auth, run_id)["status"] == "cancelled"
    finally:
        release.set()
        worker.join(15)

    run = _run(client, auth, run_id)
    assert run["status"] == "cancelled"  # the late result did not overwrite it
    assert run["artifact_path"] is None
    assert not artifact.exists()  # and the artifact it wrote was removed


def test_a_finished_run_cannot_be_cancelled(client, auth):
    run_id = _enqueue(client, auth)
    asyncio.run(main.drain_training_queue())
    assert _run(client, auth, run_id)["status"] == "completed"

    response = client.post(f"/api/v1/ml/runs/{run_id}/cancel", headers=auth)

    assert response.status_code == 409
    assert "already completed" in response.json()["detail"]


def test_only_the_owner_can_cancel_and_a_token_is_needed(client, auth, other_auth):
    run_id = _enqueue(client, auth)

    assert client.post(f"/api/v1/ml/runs/{run_id}/cancel", headers=other_auth).status_code == 404
    assert client.post(f"/api/v1/ml/runs/{run_id}/cancel").status_code == 401
    assert _run(client, auth, run_id)["status"] == "queued"
    asyncio.run(main.drain_training_queue())


def test_the_worker_does_not_touch_a_run_that_has_no_request(client, auth):
    """A queued row without a stored request is not claimable (it is swept)."""
    orphan = _insert_run(_owner_id("queue_user"), "queued", with_request=False)

    claimed = asyncio.run(main._claim_next_run())

    assert claimed is None
    _sql("UPDATE training_runs SET status = 'failed' WHERE id = ?", orphan)
