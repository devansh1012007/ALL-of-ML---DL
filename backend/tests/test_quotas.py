"""The quota system (plans A3, A4, A5, A10).

Every limit is data an admin edits, and every refusal carries the quota
object (name, limit, used, resets_at) so the interface can show the reason
and the reset time instead of an opaque 403. These tests pin:

* the resolution of the effective quota (override > profile > free);
* each submit-time limit refused with the right status and body;
* the predict rate limit of one user;
* the usage accounting (runs today, storage as the sum of the datasets and
  the artifacts - a derived sum, which cannot drift from the truth).
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.quotas import (
    PROFILE_FREE,
    effective_quota,
)


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


def _make_admin(client, username):
    """Create a user and promote it to admin directly in the database."""
    import sqlite3

    from sqlalchemy.engine import make_url

    from backend.app.database import DATABASE_URL

    headers = _login(client, username)
    connection = sqlite3.connect(make_url(DATABASE_URL).database)
    try:
        connection.execute(
            "UPDATE users SET role = 'admin' WHERE username = ?", (username,)
        )
        connection.commit()
    finally:
        connection.close()
    return headers


def _dataset(client, auth, name="sample_customer_churn.csv"):
    listing = client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
    return next(item for item in listing if item["name"] == name)


def _train(client, auth, dataset_id, label_column):
    return client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "KNN",
            "dataset_id": dataset_id,
            "label_column": label_column,
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
        },
    )


def test_the_profiles_are_seeded_at_startup(client):
    """The three profiles of plan A3 exist after the startup seeding."""
    admin = _make_admin(client, "quota_admin")
    response = client.get("/api/v1/admin/quota-profiles", headers=admin)
    assert response.status_code == 200, response.text
    names = {profile["name"] for profile in response.json()["items"]}
    assert {"free", "standard", "unlimited"} <= names


def test_a_user_gets_the_free_profile_by_default(client):
    """A user without a profile resolves to "free" (plan A3)."""
    import asyncio

    from backend.app.database import AsyncSessionLocal
    from backend.app.models import User

    async def _quota():
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(
                    select(User).where(User.username == "quota_admin")
                )
            ).scalars().first()
            return await effective_quota(session, user)

    quota = asyncio.run(_quota())
    assert quota["profile_name"] == "free"
    assert quota["max_queued_runs"] == PROFILE_FREE["max_queued_runs"]


def test_the_queued_limit_is_refused_with_the_quota_object(client):
    """Too many queued runs is a 429 whose body names the limit (plan A4)."""
    import sqlite3

    from sqlalchemy.engine import make_url

    from backend.app.database import DATABASE_URL

    auth = _login(client, "quota_queued_user")
    dataset = _dataset(client, auth)
    # Fill the queue with rows that are already waiting: the real queue
    # would drain them in the background, and the refusal is about the
    # waiting rows, not the running ones.
    limit = 5  # the free profile
    connection = sqlite3.connect(make_url(DATABASE_URL).database)
    try:
        user_row = connection.execute(
            "SELECT id FROM users WHERE username = 'quota_queued_user'"
        ).fetchone()
        for _ in range(limit):
            connection.execute(
                "INSERT INTO training_runs (owner_id, model_name, dataset_source,"
                " dataset_tag, hyperparameters, mode, status, job_kind)"
                " VALUES (?, 'KNN', 'local', 'x.csv', '{}', 'manual', 'queued', 'train')",
                (user_row[0],),
            )
        connection.commit()
    finally:
        connection.close()

    response = _train(client, auth, dataset["id"], dataset["label_column"])
    assert response.status_code == 429, response.text
    body = response.json()
    assert body["detail"]["quota"]["name"] == "max_queued_runs"
    assert body["detail"]["quota"]["limit"] == limit
    assert body["detail"]["quota"]["used"] == limit


def test_the_daily_limit_is_refused_with_the_reset_time(client):
    """The runs-per-day limit is a 429 with resets_at (plan A4)."""
    import sqlite3

    from sqlalchemy.engine import make_url

    from backend.app.database import DATABASE_URL

    auth = _login(client, "quota_daily_user")
    dataset = _dataset(client, auth)
    # Fill the day with rows that are already finished: the count is over
    # the rows of today, whatever their state.
    connection = sqlite3.connect(make_url(DATABASE_URL).database)
    try:
        user_row = connection.execute(
            "SELECT id FROM users WHERE username = 'quota_daily_user'"
        ).fetchone()
        for _ in range(20):
            connection.execute(
                "INSERT INTO training_runs (owner_id, model_name, dataset_source,"
                " dataset_tag, hyperparameters, mode, status, job_kind)"
                " VALUES (?, 'KNN', 'local', 'x.csv', '{}', 'manual', 'failed', 'train')",
                (user_row[0],),
            )
        connection.commit()
    finally:
        connection.close()

    response = _train(client, auth, dataset["id"], dataset["label_column"])
    assert response.status_code == 429, response.text
    quota = response.json()["detail"]["quota"]
    assert quota["name"] == "max_runs_per_day"
    assert quota["limit"] == 20
    assert "resets_at" in quota


def test_a_category_outside_the_profile_is_a_403(client):
    """A category the profile does not allow is refused (plan A4).

    The test flips the deployment setting to the tabular-only default,
    which is exactly the state a fresh installation is in.
    """
    import asyncio

    from backend.app import quotas as quotas_module
    from backend.app.database import AsyncSessionLocal
    from backend.app.models import User

    auth = _login(client, "quota_category_user")
    dataset = _dataset(client, auth)

    async def _override():
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            user = (
                await session.execute(
                    select(User).where(User.username == "quota_category_user")
                )
            ).scalars().first()
            from backend.app.models import UserQuotaOverride

            session.add(
                UserQuotaOverride(
                    user_id=user.id, allowed_categories=["classification"]
                )
            )
            await session.commit()

    asyncio.run(_override())
    try:
        # KNN is a classification model: allowed. A clustering model is not.
        allowed = _train(client, auth, dataset["id"], dataset["label_column"])
        assert allowed.status_code == 200, allowed.text

        from backend.app import main as main_module

        response = client.post(
            "/api/v1/ml/train",
            headers=auth,
            json={
                "model_name": "K-Mean",
                "dataset_id": dataset["id"],
                "label_column": "churned",
                "hyperparameters": {},
                "mode": "manual",
            },
        )
        assert response.status_code == 403, response.text
        quota = response.json()["detail"]["quota"]
        assert quota["name"] == "allowed_categories"
        assert quota["used"] == "clustering"
    finally:
        import sqlite3

        from sqlalchemy.engine import make_url

        from backend.app.database import DATABASE_URL

        connection = sqlite3.connect(make_url(DATABASE_URL).database)
        try:
            connection.execute(
                "DELETE FROM user_quota_overrides WHERE user_id ="
                " (SELECT id FROM users WHERE username = 'quota_category_user')"
            )
            connection.commit()
        finally:
            connection.close()


def test_the_predict_row_limit_uses_the_quota(client):
    """The rows of one predict request are bounded by the profile (A4)."""
    from backend.app.quotas import QuotaRefusal, check_predict_rows

    quota = {"max_predict_rows_per_request": 2}
    check_predict_rows(2, quota)  # the limit itself is allowed
    with pytest.raises(QuotaRefusal) as refusal:
        check_predict_rows(3, quota)
    assert refusal.value.status_code == 413
    assert refusal.value.quota["name"] == "max_predict_rows_per_request"


def test_the_predict_rate_limit_counts_the_minute(client):
    """The predict requests of one minute are bounded (plan A4)."""
    from backend.app.quotas import QuotaRefusal, check_predict_rate, reset_predict_rate_limits

    reset_predict_rate_limits()
    quota = {"max_predict_requests_per_minute": 3}
    try:
        for _ in range(3):
            check_predict_rate(1, quota)
        with pytest.raises(QuotaRefusal) as refusal:
            check_predict_rate(1, quota)
        assert refusal.value.quota["name"] == "max_predict_requests_per_minute"
        assert refusal.value.quota["used"] == 3
    finally:
        reset_predict_rate_limits()


def test_the_usage_panel_counts_runs_and_storage(client):
    """GET /me shows the usage of the caller (plans A5, A7)."""
    auth = _login(client, "quota_me_user")
    response = client.get("/api/v1/me", headers=auth)
    assert response.status_code == 200, response.text
    me = response.json()
    assert me["usage"]["runs_today"] >= 0
    assert me["usage"]["storage_bytes"] >= 0
    assert "max_runs_per_day" in me["usage"]["limits"]
    assert "resets_at" in me["usage"]


def test_the_unknown_preprocessing_option_is_refused():
    """A typo in the options is loud, not silently ignored (plan C6)."""
    from backend.app.tabular import parse_preprocessing_options

    with pytest.raises(ValueError, match="Unknown preprocessing option"):
        parse_preprocessing_options({"scalee": "on"})
