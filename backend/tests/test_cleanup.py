"""Deletion and retention (plan H1).

A user who cannot delete what they made cannot be given a storage quota. The
tests pin:

* a finished run can be deleted by its owner - the row, the artifact file
  and the charts go together;
* a queued or running run refuses (cancel first), and a run that a
  deployment serves refuses too;
* the bulk delete reports every id honestly: what went, what refused, why;
* a dataset of the repository refuses, an uploaded one goes (file and row),
  and one an active training is reading refuses;
* the self-service account deletion wants the password, refuses the last
  admin, and takes the files, the sessions and the runs with it;
* the retention of a profile retires the artifacts that fell out of its
  rules while the runs keep their metrics and show ``artifact_removed``;
* the janitor removes the files no row refers to and marks the rows whose
  file is gone.
"""

import asyncio
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import cleanup
from backend.app.main import app
from backend.app.models import Dataset, Deployment, TrainingRun, User, UserQuotaOverride


DATABASE_PATH = os.path.join(
    os.path.dirname(os.environ["DATABASE_URL"].replace("sqlite+aiosqlite:///", "")), ""
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    username = "h1_user"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _sql(query, params=()):
    """One synchronous statement against the test database.

    The suite's database is a SQLite file (conftest); the maintenance paths
    under test write through the application's own session factory, so the
    assertions read the same file.
    """
    from backend.app.settings import DATABASE_URL

    path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    connection = sqlite3.connect(path)
    try:
        with connection:
            return connection.execute(query, params).fetchall()
    finally:
        connection.close()


def _user_id(username: str) -> int:
    return _sql("SELECT id FROM users WHERE username = ?", (username,))[0][0]


def _make_run(user_id: int, status: str = "completed", with_artifact: bool = True) -> int:
    """Insert a run row directly and write a small artifact file for it."""

    async def _insert():
        from backend.app.models import TrainingRun

        factory, engine = _own_session()
        try:
            async with factory() as session:
                artifact_path = None
                if with_artifact:
                    from backend.app.model_training import MODEL_DIR

                    directory = Path(MODEL_DIR) / f"run_{user_id}_{os.urandom(3).hex()}"
                    directory.mkdir(parents=True, exist_ok=True)
                    (directory / "bundle.json").write_text("{}", encoding="utf-8")
                    artifact_path = str(directory)
                run = TrainingRun(
                    owner_id=user_id,
                    model_name="Logistic_Regression",
                    dataset_source="local",
                    dataset_tag="some-dataset",
                    hyperparameters={},
                    status=status,
                    artifact_path=artifact_path,
                    artifact_bytes=2 if artifact_path else None,
                    metrics={"score": 0.9},
                )
                session.add(run)
                await session.commit()
                return run.id
        finally:
            await engine.dispose()

    return asyncio.run(_insert())


def _dataset_id(owner_id: int, name: str, storage_path: str) -> int:
    async def _insert():
        from backend.app.models import Dataset

        factory, engine = _own_session()
        try:
            async with factory() as session:
                row = Dataset(
                    owner_id=owner_id,
                    name=name,
                    source="upload",
                    storage_path=storage_path,
                    size_bytes=10,
                    row_count=1,
                    columns=["a", "b"],
                )
                session.add(row)
                await session.commit()
                return row.id
        finally:
            await engine.dispose()

    return asyncio.run(_insert())


# --- runs ----------------------------------------------------------------------


def test_a_finished_run_is_deleted_with_its_artifact(client, auth):
    user_id = _user_id("h1_user")
    run_id = _make_run(user_id)
    artifact_path = _sql(
        "SELECT artifact_path FROM training_runs WHERE id = ?", (run_id,)
    )[0][0]
    assert artifact_path and Path(artifact_path).exists()

    response = client.delete(f"/api/v1/ml/runs/{run_id}", headers=auth)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"][0]["id"] == run_id
    assert not Path(artifact_path).exists()
    assert _sql("SELECT id FROM training_runs WHERE id = ?", (run_id,)) == []


def test_a_foreign_run_is_not_found_for_the_delete(client, auth):
    other = _make_run(_user_id("h1_user") + 100000)
    response = client.delete(f"/api/v1/ml/runs/{other}", headers=auth)
    assert response.status_code == 404
    _sql("DELETE FROM training_runs WHERE id = ?", (other,))


def test_a_queued_run_refuses_the_delete(client, auth):
    user_id = _user_id("h1_user")
    run_id = _make_run(user_id, status="queued", with_artifact=False)
    response = client.delete(f"/api/v1/ml/runs/{run_id}", headers=auth)
    assert response.status_code == 409
    assert "cancel" in response.json()["detail"]
    _sql("DELETE FROM training_runs WHERE id = ?", (run_id,))


def test_a_run_a_deployment_serves_refuses_the_delete(client, auth):
    user_id = _user_id("h1_user")
    run_id = _make_run(user_id)

    async def _deploy():
        from backend.app.models import Deployment

        factory, engine = _own_session()
        try:
            async with factory() as session:
                session.add(
                    Deployment(owner_id=user_id, name=f"prod_{run_id}", run_id=run_id)
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_deploy())

    response = client.delete(f"/api/v1/ml/runs/{run_id}", headers=auth)
    assert response.status_code == 409
    assert "deployment" in response.json()["detail"]
    _sql("DELETE FROM deployments WHERE run_id = ?", (run_id,))
    _sql("DELETE FROM training_runs WHERE id = ?", (run_id,))


def test_the_bulk_delete_reports_every_id(client, auth):
    user_id = _user_id("h1_user")
    good_1 = _make_run(user_id)
    good_2 = _make_run(user_id)
    queued = _make_run(user_id, status="queued", with_artifact=False)

    response = client.post(
        "/api/v1/ml/runs/delete-bulk",
        json={"ids": [good_1, good_2, queued, 999999]},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(item["id"] for item in body["deleted"]) == sorted([good_1, good_2])
    refused = {item["id"]: item["reason"] for item in body["refused"]}
    assert "cancel" in refused[queued]
    assert "No such run." in refused[999999]


# --- datasets ------------------------------------------------------------------


def test_a_builtin_dataset_refuses_the_delete(client, auth):
    builtin = _sql(
        "SELECT id FROM datasets WHERE owner_id IS NULL LIMIT 1"
    )
    if not builtin:
        pytest.skip("no built-in dataset registered")
    response = client.delete(f"/api/v1/ml/datasets/{builtin[0][0]}", headers=auth)
    assert response.status_code == 403


def test_an_uploaded_dataset_is_deleted_with_its_file(client, auth):
    user_id = _user_id("h1_user")
    from backend.app.settings import datasets_root

    uploads = datasets_root() / "uploads" / str(user_id)
    uploads.mkdir(parents=True, exist_ok=True)
    file_path = uploads / "h1_delete_me.csv"
    file_path.write_text("a,b\n1,2\n", encoding="utf-8")
    dataset_id = _dataset_id(user_id, f"h1_dataset_{os.urandom(2).hex()}", f"uploads/{user_id}/h1_delete_me.csv")

    response = client.delete(f"/api/v1/ml/datasets/{dataset_id}", headers=auth)
    assert response.status_code == 200, response.text
    assert not file_path.exists()
    assert _sql("SELECT id FROM datasets WHERE id = ?", (dataset_id,)) == []


def test_a_dataset_an_active_run_reads_refuses_the_delete(client, auth):
    user_id = _user_id("h1_user")
    dataset_id = _dataset_id(user_id, f"h1_busy_{os.urandom(2).hex()}", f"uploads/{user_id}/busy.csv")
    _sql(
        "INSERT INTO training_runs (owner_id, model_name, dataset_source, dataset_tag, "
        "hyperparameters, status, dataset_id, mode) VALUES (?, 'Logistic_Regression', 'local', 'x', '{}', 'queued', ?, 'manual')",
        (user_id, dataset_id),
    )
    response = client.delete(f"/api/v1/ml/datasets/{dataset_id}", headers=auth)
    assert response.status_code == 409
    _sql("DELETE FROM training_runs WHERE dataset_id = ?", (dataset_id,))
    _sql("DELETE FROM datasets WHERE id = ?", (dataset_id,))


# --- the account ---------------------------------------------------------------


def test_the_self_deletion_wants_the_password(client, auth):
    response = client.request(
        "POST", "/api/v1/users/me/delete", json={"password": "wrong-password"}, headers=auth
    )
    assert response.status_code == 400


def test_the_self_deletion_takes_everything_with_it(client):
    username = f"h1_self_{os.urandom(2).hex()}"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    login = client.post("/token", data={"username": username, "password": "secret123"})
    token = login.json()["access_token"]
    refresh = login.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = _user_id(username)

    run_id = _make_run(user_id)
    artifact_path = _sql(
        "SELECT artifact_path FROM training_runs WHERE id = ?", (run_id,)
    )[0][0]
    dataset_id = _dataset_id(user_id, f"h1_gone_{os.urandom(2).hex()}", f"uploads/{user_id}/gone.csv")

    response = client.request(
        "POST", "/api/v1/users/me/delete", json={"password": "secret123"}, headers=headers
    )
    assert response.status_code == 200, response.text

    assert _sql("SELECT id FROM users WHERE id = ?", (user_id,)) == []
    assert _sql("SELECT id FROM training_runs WHERE id = ?", (run_id,)) == []
    assert _sql("SELECT id FROM datasets WHERE id = ?", (dataset_id,)) == []
    assert _sql("SELECT id FROM refresh_tokens WHERE user_id = ?", (user_id,)) == []
    if artifact_path:
        assert not Path(artifact_path).exists()

    # The token of the deleted account is worthless, and so is the session.
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_the_last_admin_cannot_self_delete(client):
    username = f"h1_admin_{os.urandom(2).hex()}"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    # The promotion is a manual database operation (plan A1). The user must
    # be the ONLY admin: other tests may have promoted their own, and the
    # guard counts.
    _sql("UPDATE users SET role = 'user' WHERE role = 'admin'")
    _sql("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]

    response = client.request(
        "POST",
        "/api/v1/users/me/delete",
        json={"password": "secret123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409
    assert "last admin" in response.json()["detail"]


# --- retention and the janitor ---------------------------------------------------


def test_the_retention_of_a_profile_retires_the_old_artifacts(client, auth):
    user_id = _user_id("h1_user")

    async def _set_rule():
        """The retention rule is an override of the user (plan A3/H1)."""
        from sqlalchemy import select

        factory, engine = _own_session()
        try:
            async with factory() as session:
                override = (
                    await session.execute(
                        select(UserQuotaOverride).where(UserQuotaOverride.user_id == user_id)
                    )
                ).scalars().first()
                if override is None:
                    override = UserQuotaOverride(user_id=user_id)
                    session.add(override)
                override.artifact_keep_runs = 1
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_set_rule())
    try:
        old_run = _make_run(user_id)
        new_run = _make_run(user_id)
        # The created_at of the two runs is set by the clock; make the first
        # one clearly older so the "last 1" rule has an unambiguous answer.
        # The timestamp format must match the one SQLAlchemy writes (a space
        # separator, not an ISO 'T'): the column is compared as a string.
        _sql(
            "UPDATE training_runs SET created_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S.%f"), old_run),
        )

        asyncio.run(_retention_on_app_session())
        removed_ids = _sql(
            "SELECT id FROM training_runs WHERE artifact_removed_at IS NOT NULL AND owner_id = ?",
            (user_id,),
        )
        assert old_run in [row[0] for row in removed_ids]
        assert new_run not in [row[0] for row in removed_ids]
        # The metrics survived the retirement.
        metrics = _sql("SELECT metrics FROM training_runs WHERE id = ?", (old_run,))[0][0]
        assert metrics and "score" in metrics
    finally:
        _clear_rule()
        _sql("DELETE FROM training_runs WHERE owner_id = ?", (user_id,))


def _own_session():
    """A session factory on its own engine, safe inside ``asyncio.run``.

    The application engine binds its connections to the loop that created
    them; a helper that runs on a fresh loop brings its own engine, so no
    pooled connection is ever asked to serve two loops.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.settings import DATABASE_URL

    engine = create_async_engine(DATABASE_URL)
    return sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False), engine


async def _retention_on_app_session():
    from backend.app import cleanup as cleanup_module

    factory, engine = _own_session()
    try:
        async with factory() as session:
            summary = await cleanup_module.apply_retention(session)
            await session.commit()
            return summary
    finally:
        await engine.dispose()


def _clear_rule():
    async def _go():
        from sqlalchemy import delete

        factory, engine = _own_session()
        try:
            async with factory() as session:
                await session.execute(delete(UserQuotaOverride))
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(_go())


def test_the_janitor_removes_orphaned_files_and_marks_missing_ones(client, auth):
    user_id = _user_id("h1_user")
    # A run whose artifact file somebody deleted behind the application's back.
    run_id = _make_run(user_id)
    artifact_path = _sql(
        "SELECT artifact_path FROM training_runs WHERE id = ?", (run_id,)
    )[0][0]
    import shutil

    shutil.rmtree(artifact_path, ignore_errors=True)

    # A file in the models tree that no row refers to.
    from backend.app.model_training import MODEL_DIR

    orphan_dir = Path(MODEL_DIR) / f"orphan_{os.urandom(3).hex()}"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "bundle.json").write_text("{}", encoding="utf-8")

    marked_missing = asyncio.run(_janitor_on_app_session())["marked_missing"]

    assert marked_missing >= 1
    # The janitor removes the files, not the directory that held them.
    assert not (orphan_dir / "bundle.json").exists()
    assert _sql(
        "SELECT artifact_removed_at FROM training_runs WHERE id = ?", (run_id,)
    )[0][0] is not None
    _sql("DELETE FROM training_runs WHERE id = ?", (run_id,))


async def _janitor_on_app_session():
    from backend.app import cleanup as cleanup_module

    factory, engine = _own_session()
    try:
        async with factory() as session:
            summary = await cleanup_module.janitor_sweep(session)
            await session.commit()
            return summary
    finally:
        await engine.dispose()
