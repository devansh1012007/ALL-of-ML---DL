"""API-level regression tests for the authentication and the run history.

They lock in the contracts of the API:

* every ML endpoint requires a valid token: a request without an
  ``Authorization`` header is rejected with 401;
* a request with an **invalid** credential is rejected with 401 as well;
* a registration cannot choose its own role, a duplicate registration is a
  conflict (409) not a server error, and it must not break the session;
* the credential policy is enforced and the reserved names are refused;
* the run history exposes the mode and the environment of a run next to the
  fields it always exposed;
* an auto-search on a regression dataset picks the better candidate instead of
  the first one.

The database is the isolated one of ``conftest.py``; the rows are inspected
with the standard library ``sqlite3`` module so that no second event loop (and
no second connection to the same SQLite file) is needed.
"""

import os
import sqlite3
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.engine import make_url

from backend.app.auth import ALGORITHM, SECRET_KEY
from backend.app.main import app

DATABASE_PATH = make_url(os.environ["DATABASE_URL"]).database

# The fields the run endpoints exposed before the mode/env_id were added. They
# must not disappear when new fields are added.
PRE_EXISTING_LIST_KEYS = {
    "id",
    "model_name",
    "dataset_source",
    "dataset_tag",
    "status",
    "artifact_path",
    "metrics",
    "created_at",
    "updated_at",
}
PRE_EXISTING_DETAIL_KEYS = PRE_EXISTING_LIST_KEYS | {"hf_dataset_url", "hyperparameters"}


@pytest.fixture(scope="module")
def client():
    """A TestClient that runs the lifespan (so the tables exist)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    """The headers of a registered, logged-in user.

    Every ML endpoint requires a token, so the tests that talk to them need
    one. The user is registered once for the module.
    """
    username = "test_user"
    client.post(
        "/api/v1/register", json={"username": username, "password": "secret123"}
    )
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _query(sql, params=()):
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        # The context manager commits the statement, otherwise an INSERT/UPDATE
        # would be rolled back when the connection is closed.
        with connection:
            return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def _user_rows(username):
    return _query("SELECT id, username, role FROM users WHERE username = ?", (username,))


def _token(payload):
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _valid_token(username="test_user"):
    return _token({"sub": username, "exp": datetime.utcnow() + timedelta(hours=1)})


def _expired_token(username="test_user"):
    return _token({"sub": username, "exp": datetime.utcnow() - timedelta(hours=1)})


def _tampered_token(username="test_user"):
    header, payload, signature = _valid_token(username).split(".")
    return f"{header}.{payload}.{'A' * len(signature)}"


def test_requests_without_authorization_header_are_rejected(client):
    """Every ML endpoint needs a token.

    The previous behaviour - falling back to a shared ``anonymous`` account -
    meant that all the unauthenticated callers shared one history and that the
    account could be logged into with the password ``anonymous``.
    """
    models = client.get("/api/v1/ml/models")
    runs = client.get("/api/v1/ml/runs")

    assert models.status_code == 401
    assert runs.status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer not-a-token",
        "Bearer",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        "not-a-scheme token",
    ],
)
def test_malformed_credentials_are_rejected(client, authorization):
    """A malformed credential is a 401."""
    response = client.get("/api/v1/ml/models", headers={"Authorization": authorization})

    assert response.status_code == 401


@pytest.mark.parametrize("token_factory", [_expired_token, _tampered_token])
def test_invalid_tokens_are_rejected(client, auth, token_factory):
    """An expired or tampered token is a 401."""
    response = client.get(
        "/api/v1/ml/models", headers={"Authorization": f"Bearer {token_factory()}"}
    )

    assert response.status_code == 401


def test_a_valid_token_is_accepted(client, auth):
    """The token of a registered user opens the ML endpoints."""
    response = client.get("/api/v1/ml/models", headers=auth)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_the_anonymous_account_cannot_be_used(client):
    """The shared anonymous account is gone.

    It used to be created on the first token-less request and to be
    loggable with the password ``anonymous``.
    """
    assert _user_rows("anonymous") == []

    login = client.post("/token", data={"username": "anonymous", "password": "anonymous"})
    assert login.status_code == 400


@pytest.mark.parametrize("username", ["anonymous", "admin", "root", "system"])
def test_the_reserved_usernames_cannot_be_registered(client, username):
    """A reserved name is refused."""
    registration = client.post(
        "/api/v1/register", json={"username": username, "password": "secret123"}
    )

    assert registration.status_code == 400
    assert _user_rows(username) == []


def test_a_short_password_is_refused(client):
    """The credential policy is enforced."""
    registration = client.post(
        "/api/v1/register", json={"username": "short_password", "password": "short"}
    )

    assert registration.status_code == 400
    assert _user_rows("short_password") == []


def test_the_login_is_rate_limited(client):
    """A client that tries too many passwords is stopped."""
    for _ in range(20):
        client.post("/token", data={"username": "guessed", "password": "guessed"})

    response = client.post("/token", data={"username": "guessed", "password": "guessed"})
    assert response.status_code == 429, response.text


def test_token_of_a_deleted_user_is_rejected(client):
    """A token whose user no longer exists is a 401."""
    username = "deleted_user"
    registration = client.post(
        "/api/v1/register", json={"username": username, "password": "secret123"}
    )
    assert registration.status_code == 200
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]

    _query("DELETE FROM users WHERE username = ?", (username,))

    response = client.get("/api/v1/ml/models", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_duplicate_registration_is_a_conflict_and_keeps_the_session_usable(client):
    """A duplicate username is a 409, the session survives it."""
    first = client.post(
        "/api/v1/register", json={"username": "duplicate_user", "password": "secret123"}
    )
    second = client.post(
        "/api/v1/register", json={"username": "duplicate_user", "password": "secret123"}
    )
    # The failed registration must not have poisoned the session.
    third = client.post(
        "/api/v1/register", json={"username": "second_user", "password": "secret123"}
    )
    login = client.post(
        "/token", data={"username": "second_user", "password": "secret123"}
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert third.status_code == 200
    assert login.status_code == 200
    assert login.json()["access_token"]
    assert len(_user_rows("duplicate_user")) == 1


def test_registration_never_stores_a_client_supplied_role(client):
    """A client may not promote itself to admin."""
    registration = client.post(
        "/api/v1/register",
        json={"username": "admin_wannabe", "password": "secret123", "role": "admin"},
    )
    assert registration.status_code == 200

    rows = _user_rows("admin_wannabe")
    assert len(rows) == 1
    assert rows[0][2] == "user"

    token = client.post(
        "/token", data={"username": "admin_wannabe", "password": "secret123"}
    ).json()["access_token"]
    admin_listing = client.get(
        "/api/v1/admin/all-users", headers={"Authorization": f"Bearer {token}"}
    )
    assert admin_listing.status_code == 403


def _upload_dataset(client, auth, storage_path):
    """Upload a dataset and return its row.

    The datasets of the test run live in the temporary datasets root, and a
    training request refers to a dataset by its id, so the test uploads the
    file first - the same way a user would.
    """
    from pathlib import Path

    content = (Path(os.environ["DATASETS_ROOT"]) / storage_path).read_bytes()
    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": (Path(storage_path).name, content, "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_run_history_exposes_the_mode_and_the_environment(
    client, auth, classification_dataset
):
    """The run history exposes the mode and env_id next to the old fields."""
    dataset = _upload_dataset(client, auth, classification_dataset)
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Logistic_Regression",
            "dataset_id": dataset["id"],
            "label_column": "label",
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
        },
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]

    # The environment of a run is stored with the run.
    _query("UPDATE training_runs SET env_id = ? WHERE id = ?", ("CartPole-v1", run_id))

    listing = client.get("/api/v1/ml/runs", headers=auth)
    assert listing.status_code == 200
    runs = listing.json()
    run = next(item for item in runs if item["id"] == run_id)
    assert PRE_EXISTING_LIST_KEYS <= set(run)
    assert "mode" in run
    assert "env_id" in run
    assert run["mode"] == "manual"
    assert run["env_id"] == "CartPole-v1"

    detail = client.get(f"/api/v1/ml/runs/{run_id}", headers=auth)
    assert detail.status_code == 200
    detail_run = detail.json()
    assert PRE_EXISTING_DETAIL_KEYS <= set(detail_run)
    assert "mode" in detail_run
    assert "env_id" in detail_run
    assert detail_run["mode"] == "manual"
    assert detail_run["env_id"] == "CartPole-v1"


def test_auto_search_picks_the_better_candidate_on_a_regression_dataset(
    client, auth, regression_dataset, wait_for_run
):
    """A regression run must be ranked on a metric it really reports.

    The candidates are ordered so that the *first* one is the worse model: with
    the accuracy fallback every candidate scores 0 and the first one wins.
    """
    dataset = _upload_dataset(client, auth, regression_dataset)
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "MLR",
            "dataset_id": dataset["id"],
            "label_column": "label",
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "auto_search",
            "optimize_metric": "accuracy",
            "model_candidates": ["KNN", "MLR"],
        },
    )

    assert response.status_code == 200, response.text
    # The training runs in the background: the result is read from the run.
    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "completed", run
    metrics = run["metrics"]
    assert metrics["best_candidate"] == "MLR"
    assert metrics["task_type"] == "regression"
    assert metrics["r2"] > 0.9
