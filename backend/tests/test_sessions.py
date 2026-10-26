"""The browser session endpoints (plan A2, the second half).

They pin the lifecycle: the login issues a refresh token (cookie for the
browser, body for programmatic clients), refreshing rotates it, presenting a
rotated token kills the whole family, the logout ends the session, and the
password change ends every session of the account and bumps the
``token_version`` that the access tokens carry.
"""

import os

import pytest
from fastapi.testclient import TestClient

from backend.app.auth import ACCESS_TOKEN_MINUTES
from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _fresh_cookies(client):
    """A cookie of the previous test must not ride along.

    The refresh token prefers the cookie over the body - that is the right
    order for a browser - so a stale cookie of a previous test would answer
    before the body of this one. Each test starts with an empty jar.
    """
    client.cookies.clear()
    yield
    client.cookies.clear()


def _login(client, username="sess_user", password="secret123"):
    registered = client.post(
        "/api/v1/register", json={"username": username, "password": password}
    )
    if registered.status_code == 409:
        username = f"{username}_{os.urandom(2).hex()}"
        client.post("/api/v1/register", json={"username": username, "password": password})
    response = client.post("/token", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_login_issues_a_refresh_token_and_the_cookie(client):
    payload = _login(client, username="sess_issue")
    assert "refresh_token" in payload
    assert payload["expires_in"] == ACCESS_TOKEN_MINUTES * 60
    assert client.cookies.get("refresh_token") is not None


def test_the_refresh_cookie_is_httponly_strict_and_narrow(client):
    username = "sess_flags"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    response = client.post("/token", data={"username": username, "password": "secret123"})
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()
    assert "path=/api/v1/auth" in set_cookie.lower()


def test_a_refresh_rotates_and_the_new_token_works(client):
    payload = _login(client, username="sess_rotate")
    old_refresh = payload["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    # The rotation is about the refresh token: the access token may well be
    # byte-identical (same claims, same second) - what matters is that the
    # presented refresh token was replaced and the old one can never be
    # presented again.
    assert body["refresh_token"] != old_refresh

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"].startswith("sess_rotate")


def test_presenting_a_rotated_token_revokes_the_family(client):
    """The reuse-detection rule (plan A2): the second presentation of the same
    token is the signature of a theft, so the fresh copy dies with it."""
    payload = _login(client, username="sess_reuse")
    first_refresh = payload["refresh_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200
    second_refresh = rotated.json()["refresh_token"]

    # The replay carries no cookie: the cookie of the client is the *current*
    # session, and a browser replaying a stolen copy would not have it. The
    # body token is what the attacker presents.
    client.cookies.clear()

    # The attacker replays the first token; the family dies.
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert replay.status_code == 401

    # The victim's fresh token is dead too.
    victim = client.post("/api/v1/auth/refresh", json={"refresh_token": second_refresh})
    assert victim.status_code == 401


def test_an_unknown_refresh_token_is_refused(client):
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
    )
    assert response.status_code == 401


def test_the_cookie_alone_can_refresh(client):
    _login(client, username="sess_cookie")
    # The TestClient keeps the cookie; no body is sent.
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200, response.text
    assert "access_token" in response.json()


def test_the_logout_revokes_the_session(client):
    payload = _login(client, username="sess_logout")
    refresh = payload["refresh_token"]

    out = client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 200

    again = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert again.status_code == 401


def test_the_password_change_ends_every_session(client):
    username = "sess_password"
    payload = _login(client, username=username)
    first_access = payload["access_token"]
    first_refresh = payload["refresh_token"]

    # A second session of the same account, as a second browser would have.
    second_login = client.post("/token", data={"username": username, "password": "secret123"})
    second_refresh = second_login.json()["refresh_token"]

    # A wrong current password changes nothing.
    wrong = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "not-the-password", "new_password": "newsecret456"},
        headers={"Authorization": f"Bearer {first_access}"},
    )
    assert wrong.status_code == 400

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "secret123", "new_password": "newsecret456"},
        headers={"Authorization": f"Bearer {first_access}"},
    )
    assert changed.status_code == 200, changed.text

    # The token that was used for the change carries the old version: it is
    # dead at the next request, even though it has not expired.
    stale = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {first_access}"}
    )
    assert stale.status_code == 401

    # The fresh token works.
    fresh_access = changed.json()["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {fresh_access}"})
    assert me.status_code == 200

    # Both refresh tokens died with the change.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second_refresh}).status_code == 401

    # The new password logs in; the old one does not.
    old_login = client.post("/token", data={"username": username, "password": "secret123"})
    assert old_login.status_code == 400
    new_login = client.post("/token", data={"username": username, "password": "newsecret456"})
    assert new_login.status_code == 200


def test_the_password_change_enforces_the_policy(client):
    username = "sess_policy"
    payload = _login(client, username=username)
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "secret123", "new_password": "short"},
        headers=headers,
    )
    assert response.status_code == 400
    assert "8" in response.json()["detail"]
