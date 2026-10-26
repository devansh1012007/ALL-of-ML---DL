"""The execution layer (plans B1, B2, B3, B4).

The interface is the point: the queue decides *what* runs, the executor
decides *how*. The tests pin:

* the thread executor is the default and keeps the old contract (a cancel
  frees the slot when the thread ends; a monkeypatched ``train_model`` is
  the one that runs);
* the subprocess executor runs one fresh interpreter per training, the fake
  runner's result lands in the run row, and its events land in the table;
* the wall-clock limit stops a run that exceeds it, with the reason;
* a cancel stops the child and frees the slot at once;
* the events endpoint returns the stream in order, and the cap holds.
"""

import asyncio
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from backend.app import executor as executor_module
from backend.app import progress
from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    username = "exec_user"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def subprocess_executor(monkeypatch):
    """Point the process at the subprocess executor and the fake runner."""
    monkeypatch.setattr(executor_module, "_EXECUTOR", None)
    monkeypatch.setenv("TRAINING_EXECUTOR", "subprocess")
    monkeypatch.setenv("TRAINING_RUNNER", "tests.fake_runner")
    # The child is a fresh interpreter: the repository root has to be on its
    # path (``backend.app``), and so does the backend directory (the fake
    # runner is ``tests.fake_runner``, a package under backend/).
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    backend_dir = os.path.join(repo_root, "backend")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        [repo_root, backend_dir] + [p for p in [os.environ.get("PYTHONPATH", "")] if p]
    ))
    yield
    monkeypatch.setattr(executor_module, "_EXECUTOR", None)


def _submit(client, auth, model="Logistic_Regression", dataset_id=None, **overrides):
    body = {"model_name": model, "dataset_id": dataset_id, "test_size": 0.2}
    body.update(overrides)
    response = client.post("/api/v1/ml/train", json=body, headers=auth)
    assert response.status_code in (200, 201), response.text
    return response.json()["run_id"]


def _wait_for_status(client, auth, run_id, statuses, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/ml/runs/{run_id}", headers=auth).json()
        if run.get("status") in statuses:
            return run
        time.sleep(0.1)
    raise AssertionError(f"the run {run_id} never reached {statuses}: {run}")


def _upload_dataset(client, auth):
    response = client.post(
        "/api/v1/ml/datasets/upload",
        files={"file": ("exec.csv", b"a,b,label\n1,2,0\n3,4,1\n5,6,0\n7,8,1\n", "text/csv")},
        headers=auth,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


# --- B1: the choice -------------------------------------------------------------


def test_the_thread_executor_is_the_default(monkeypatch):
    monkeypatch.setattr(executor_module, "_EXECUTOR", None)
    monkeypatch.delenv("TRAINING_EXECUTOR", raising=False)
    assert executor_module.choose_executor().name == "thread"


def test_an_unknown_executor_is_refused(monkeypatch):
    monkeypatch.setattr(executor_module, "_EXECUTOR", None)
    monkeypatch.setenv("TRAINING_EXECUTOR", "teleport")
    with pytest.raises(RuntimeError, match="TRAINING_EXECUTOR"):
        executor_module.choose_executor()


def test_the_thread_executor_calls_what_the_process_patched(monkeypatch, client, auth):
    """The suite patches ``main.train_model``; the executor must call it."""
    from backend.app import main as main_module

    calls = []

    def fake_train(*args):
        calls.append(args)
        return ({"score": 1.0}, "local", "tag", None)

    monkeypatch.setattr(main_module, "train_model", fake_train)
    dataset_id = _upload_dataset(client, auth)
    run_id = _submit(client, auth, dataset_id=dataset_id)
    _wait_for_status(client, auth, run_id, {"completed", "failed"})

    assert len(calls) == 1


# --- B2: one process per training ------------------------------------------------


def test_the_subprocess_executor_completes_a_run(client, auth, subprocess_executor, monkeypatch):
    monkeypatch.setenv("FAKE_RUNNER_MODE", "ok")
    dataset_id = _upload_dataset(client, auth)
    run_id = _submit(client, auth, dataset_id=dataset_id)

    run = _wait_for_status(client, auth, run_id, {"completed", "failed"})
    assert run["status"] == "completed", run.get("metrics")
    assert run["metrics"]["score"] == 0.5
    assert run["artifact_path"], "the artifact of the fake runner"

    # The events of the child reached the table.
    events = client.get(f"/api/v1/ml/runs/{run_id}/events", headers=auth).json()
    kinds = [event["kind"] for event in events["events"]]
    assert "phase" in kinds
    assert "metric" in kinds
    assert events["last_seq"] >= events["events"][-1]["seq"]


def test_a_wall_clock_limit_stops_a_slow_run(client, auth, subprocess_executor, monkeypatch):
    monkeypatch.setenv("FAKE_RUNNER_MODE", "slow")
    # The override of plan A3: this user's runs get 3 seconds.
    from backend.app.models import User, UserQuotaOverride
    from backend.app.database import AsyncSessionLocal
    from sqlalchemy import select as _select

    async def _limit():
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(_select(User).where(User.username == "exec_user"))
            ).scalars().first()
            override = (
                await session.execute(
                    _select(UserQuotaOverride).where(UserQuotaOverride.user_id == user.id)
                )
            ).scalars().first()
            if override is None:
                override = UserQuotaOverride(user_id=user.id)
                session.add(override)
            override.max_run_seconds = 3
            await session.commit()

    asyncio.run(_limit())
    try:
        dataset_id = _upload_dataset(client, auth)
        run_id = _submit(client, auth, dataset_id=dataset_id)
        run = _wait_for_status(client, auth, run_id, {"failed", "completed"}, timeout=90)
        assert run["status"] == "failed"
        assert "wall-clock" in (run["metrics"].get("error") or ""), run["metrics"]
    finally:
        async def _clear():
            async with AsyncSessionLocal() as session:
                from sqlalchemy import delete as _delete

                await session.execute(_delete(UserQuotaOverride))
                await session.commit()

        asyncio.run(_clear())


def test_a_cancel_stops_the_child_and_frees_the_slot(client, auth, subprocess_executor, monkeypatch):
    monkeypatch.setenv("FAKE_RUNNER_MODE", "hang")
    dataset_id = _upload_dataset(client, auth)
    run_id = _submit(client, auth, dataset_id=dataset_id)
    _wait_for_status(client, auth, run_id, {"running"}, timeout=30)

    started = time.monotonic()
    cancelled = client.post(f"/api/v1/ml/runs/{run_id}/cancel", headers=auth)
    assert cancelled.status_code in (200, 202), cancelled.text

    run = _wait_for_status(client, auth, run_id, {"cancelled"}, timeout=60)
    assert run["status"] == "cancelled"
    # The slot is free at once: the subprocess executor returned in seconds,
    # not when the (sleeping) thread would have ended. The bound is generous
    # because a loaded machine starts the child slowly; the point is that it
    # is not the ten minutes the fake would have slept.
    assert time.monotonic() - started < 60

    # A new run starts while the corpse of the first is barely cold: the
    # slot was genuinely freed, not queued behind a zombie.
    monkeypatch.setenv("FAKE_RUNNER_MODE", "ok")
    second = _submit(client, auth, dataset_id=dataset_id)
    _wait_for_status(client, auth, second, {"completed", "failed"}, timeout=60)


def test_a_failure_of_the_child_reaches_the_run_row(client, auth, subprocess_executor, monkeypatch):
    monkeypatch.setenv("FAKE_RUNNER_MODE", "fail")
    dataset_id = _upload_dataset(client, auth)
    run_id = _submit(client, auth, dataset_id=dataset_id)
    run = _wait_for_status(client, auth, run_id, {"failed"}, timeout=90)
    assert "fake runner failed" in (run["metrics"].get("error") or "")


# --- B4: the events ---------------------------------------------------------------


def test_the_events_are_ordered_and_carry_the_last_seq(client, auth):
    dataset_id = _upload_dataset(client, auth)
    run_id = _submit(client, auth, dataset_id=dataset_id)
    _wait_for_status(client, auth, run_id, {"completed", "failed"})

    response = client.get(f"/api/v1/ml/runs/{run_id}/events?after=0", headers=auth)
    assert response.status_code == 200
    body = response.json()
    seqs = [event["seq"] for event in body["events"]]
    assert seqs == sorted(seqs)
    assert body["last_seq"] == (seqs[-1] if seqs else 0)

    # after=<last> returns nothing new.
    again = client.get(
        f"/api/v1/ml/runs/{run_id}/events?after={body['last_seq']}", headers=auth
    ).json()
    assert again["events"] == []


def test_a_foreign_run_has_no_events(client, auth):
    response = client.get("/api/v1/ml/runs/9999999/events", headers=auth)
    assert response.status_code == 404


def test_the_cap_keeps_the_last_events():
    """The cap of plan B4: a chatty trainer cannot fill the table."""
    async def _scenario():
        from backend.app.database import AsyncSessionLocal
        from backend.app.models import TrainingRun, User

        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(
                    _select_user_by_name("exec_user")
                )
            ).scalars().first()
            run = TrainingRun(
                owner_id=user.id,
                model_name="Logistic_Regression",
                dataset_source="local",
                dataset_tag="cap-test",
                hyperparameters={},
                status="completed",
            )
            session.add(run)
            await session.commit()
            run_id = run.id

        original_max = progress.MAX_EVENTS_PER_RUN
        progress.MAX_EVENTS_PER_RUN = 10
        try:
            sink = progress.DatabaseSink(run_id)
            for index in range(25):
                sink.append("metric", {"step": index})
            written = await sink.flush()
            assert written == 25
            async with AsyncSessionLocal() as session:
                from sqlalchemy import func as _func, select as _select

                count = (
                    await session.execute(
                        _select(_func.count()).select_from(
                            __import__("backend.app.models", fromlist=["RunEvent"]).RunEvent
                        ).where(
                            __import__("backend.app.models", fromlist=["RunEvent"]).RunEvent.run_id == run_id
                        )
                    )
                ).scalar_one()
            assert count == 10
        finally:
            progress.MAX_EVENTS_PER_RUN = original_max
            async with AsyncSessionLocal() as session:
                from sqlalchemy import delete as _delete

                await session.execute(_delete_run_events())
                await session.execute(_delete_training_run(run_id))
                await session.commit()

    asyncio.run(_scenario())


# --- helpers for the cap test -----------------------------------------------------


def _select_user_by_name(name):
    from sqlalchemy import select

    from backend.app.models import User

    return select(User).where(User.username == name)


def _delete_run_events():
    from sqlalchemy import delete

    from backend.app.models import RunEvent

    return delete(RunEvent)


def _delete_training_run(run_id):
    from sqlalchemy import delete

    from backend.app.models import TrainingRun

    return delete(TrainingRun).where(TrainingRun.id == run_id)
