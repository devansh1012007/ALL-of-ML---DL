"""The admin API (plans A6, A9, A10).

An admin who can only list users cannot do the job. These tests pin the
surface the admin screen is built on:

* the users, paginated, with their status and profile;
* the lifecycle: approve a pending account, suspend one, and the suspended
  user's existing token stops working at the next request (the row is
  re-read every time, the token never has to expire);
* the last admin cannot be deleted or demoted (a lock-out that would need
  a database edit to undo);
* the usage of every account, the quota profiles, the queue with a cancel
  that works on any run, the invites;
* the audit trail of every privileged change;
* the role guard: none of it is reachable without the admin role.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login(client, username, password="secret123"):
    client.post("/api/v1/register", json={"username": username, "password": password})
    token = client.post(
        "/token", data={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin(client):
    """A user promoted to admin directly in the database (the manual edit
    the create-admin command replaces in production, kept here because the
    tests may not run the command)."""
    import sqlite3

    from sqlalchemy.engine import make_url

    from backend.app.database import DATABASE_URL

    headers = _login(client, "admin_screen_user")
    connection = sqlite3.connect(make_url(DATABASE_URL).database)
    try:
        connection.execute(
            "UPDATE users SET role = 'admin' WHERE username = 'admin_screen_user'"
        )
        connection.commit()
    finally:
        connection.close()
    return headers


@pytest.fixture(scope="module")
def plain_user(client):
    return _login(client, "plain_screen_user")


def test_the_admin_routes_need_the_role(client, plain_user):
    """Every admin route refuses a non-admin (plan A10)."""
    for call in (
        lambda: client.get("/api/v1/admin/users", headers=plain_user),
        lambda: client.get("/api/v1/admin/usage", headers=plain_user),
        lambda: client.get("/api/v1/admin/queue", headers=plain_user),
        lambda: client.get("/api/v1/admin/invites", headers=plain_user),
        lambda: client.get("/api/v1/admin/audit", headers=plain_user),
        lambda: client.get("/api/v1/admin/quota-profiles", headers=plain_user),
    ):
        assert call().status_code == 403


def test_the_users_are_listed_with_their_status(client, admin, plain_user):
    response = client.get("/api/v1/admin/users", headers=admin)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "the admin sees no user"
    entry = next(item for item in items if item["username"] == "plain_screen_user")
    assert entry["status"] == "active"
    assert entry["role"] == "user"


def test_a_suspended_users_token_stops_working_at_once(client, admin):
    """Suspension increments token_version: the token the user already
    holds is refused at the next request (plans A1, A2, A10)."""
    victim = _login(client, "suspend_me_user")
    # The victim can act before the suspension.
    assert client.get("/api/v1/ml/models", headers=victim).status_code == 200

    users = client.get("/api/v1/admin/users", headers=admin).json()["items"]
    victim_id = next(u["id"] for u in users if u["username"] == "suspend_me_user")
    suspended = client.post(f"/api/v1/admin/users/{victim_id}/suspend", headers=admin)
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"

    # The very same token is refused now.
    assert client.get("/api/v1/ml/models", headers=victim).status_code == 401
    # And the login is too, with the generic message (no status oracle).
    login = client.post(
        "/token", data={"username": "suspend_me_user", "password": "secret123"}
    )
    assert login.status_code == 400
    assert login.json()["detail"] == "Incorrect username or password"


def test_an_admin_can_reinstate_a_suspended_account(client, admin):
    users = client.get("/api/v1/admin/users", headers=admin).json()["items"]
    victim_id = next(u["id"] for u in users if u["username"] == "suspend_me_user")
    patched = client.patch(
        f"/api/v1/admin/users/{victim_id}",
        headers=admin,
        json={"status": "active"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "active"
    # A fresh login works again (the suspension is reversible, A1).
    token = client.post(
        "/token", data={"username": "suspend_me_user", "password": "secret123"}
    ).json()["access_token"]
    assert client.get(
        "/api/v1/ml/models", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 200


def test_the_last_admin_cannot_be_deleted_or_demoted(client, admin):
    """The lock-out guard of plan A6."""
    users = client.get("/api/v1/admin/users", headers=admin).json()["items"]
    admin_ids = [u["id"] for u in users if u["role"] == "admin"]
    assert admin_ids, "the fixture admin is missing"
    for admin_id in admin_ids:
        # Delete the last admin: refused.
        response = client.delete(f"/api/v1/admin/users/{admin_id}", headers=admin)
        if len(admin_ids) == 1:
            assert response.status_code == 409
        else:
            assert response.status_code in (200, 409)
    # Demote the last admin: refused as well.
    response = client.patch(
        f"/api/v1/admin/users/{admin_ids[0]}", headers=admin, json={"role": "user"}
    )
    assert response.status_code == 409


def test_the_usage_of_every_account_is_listed(client, admin):
    response = client.get("/api/v1/admin/usage", headers=admin)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    entry = next(u for u in items if u["username"] == "plain_screen_user")
    assert "runs_today" in entry
    assert "storage_bytes" in entry
    assert "near_limits" in entry


def test_a_quota_profile_can_be_edited(client, admin):
    """The limits are data: an edit changes what the next request enforces."""
    profiles = client.get("/api/v1/admin/quota-profiles", headers=admin).json()["items"]
    free = next(p for p in profiles if p["name"] == "free")
    edited = client.put(
        f"/api/v1/admin/quota-profiles/{free['id']}",
        headers=admin,
        json={"values": {"max_queued_runs": 5}},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["max_queued_runs"] == 5
    assert edited.json()["max_runs_per_day"] == free["max_runs_per_day"]


def test_the_queue_lists_the_waiting_runs_and_cancels_any(client, admin, plain_user):
    """The admin queue view (plan A6): what the machine is doing."""
    import sqlite3

    from sqlalchemy.engine import make_url

    from backend.app.database import DATABASE_URL

    # A queued row of another user: only the admin can cancel it.
    connection = sqlite3.connect(make_url(DATABASE_URL).database)
    try:
        owner = connection.execute(
            "SELECT id FROM users WHERE username = 'plain_screen_user'"
        ).fetchone()[0]
        cursor = connection.execute(
            "INSERT INTO training_runs (owner_id, model_name, dataset_source,"
            " dataset_tag, hyperparameters, mode, status, job_kind)"
            " VALUES (?, 'KNN', 'local', 'x.csv', '{}', 'manual', 'queued', 'train')",
            (owner,),
        )
        run_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    queue = client.get("/api/v1/admin/queue", headers=admin).json()["items"]
    assert any(item["id"] == run_id for item in queue)
    assert all(item["owner"] for item in queue)

    cancelled = client.post(f"/api/v1/admin/queue/{run_id}/cancel", headers=admin)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancelled"] is True

    # The owner cannot cancel the runs of someone else either: the admin
    # route is the only shared cancel (the owner route stays owner-only).
    assert client.get("/api/v1/admin/queue", headers=plain_user).status_code == 403


def test_an_invite_can_be_created_and_listed(client, admin):
    """The one-time registration codes of plan A1."""
    created = client.post(
        "/api/v1/admin/invites",
        headers=admin,
        json={"max_uses": 3, "expires_days": 7},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["code"] and body["max_uses"] == 3

    listed = client.get("/api/v1/admin/invites", headers=admin).json()["items"]
    assert any(item["id"] == body["id"] for item in listed)
    assert all(not item["expired"] for item in listed if item["id"] == body["id"])


def test_the_audit_trail_records_the_privileged_changes(client, admin):
    """Every privileged change leaves an event (plan A9)."""
    events = client.get("/api/v1/admin/audit", headers=admin).json()["items"]
    actions = {event["action"] for event in events}
    assert "admin.user.suspended" in actions
    assert "admin.quota_profile.edited" in actions
    assert "admin.invite.created" in actions
    assert "admin.run.cancelled" in actions
    # The events carry their actor.
    assert any(event["actor_id"] is not None for event in events)


def test_the_registration_mode_is_open_by_default(client):
    """The default deployment is open (plan A1): a registration is active."""
    response = client.post(
        "/api/v1/register", json={"username": "open_mode_user", "password": "secret123"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"
