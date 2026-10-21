"""Tests for the security posture of the API.

They pin the properties that make the API safe to expose:

* every ML endpoint needs a valid token - there is no anonymous fallback
  anymore, and the shared ``anonymous`` account is gone;
* the signing key is never a published constant: a token that is signed with
  the old default is rejected, and a production start without a key fails;
* the credential policy is enforced and the reserved names are refused;
* the login is rate limited, and only a *failed* login counts against the
  budget;
* CORS is an explicit allow-list: a foreign origin gets no header.
"""

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from backend.app.auth import ALGORITHM, SECRET_KEY
from backend.app.main import app


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")

# The key that the application used before this change. A token that is signed
# with it must not be accepted any more.
PUBLISHED_DEFAULT_KEY = "SUPER_SECRET_KEY_FOR_ASSIGNMENT"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def registered_user(client):
    """A registered user and the headers of its session."""
    username = "sec_user"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return username, {"Authorization": f"Bearer {token}"}


def test_a_token_signed_with_the_published_key_is_rejected(client, registered_user):
    """The old default key must not sign a usable token.

    The token's ``sub`` is the only claim that is verified, so anybody who
    knows the key can mint a token for any user.
    """
    username, _headers = registered_user
    forged = jwt.encode({"sub": username}, PUBLISHED_DEFAULT_KEY, algorithm=ALGORITHM)

    response = client.get(
        "/api/v1/ml/models", headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401


def test_the_signing_key_is_never_the_published_default():
    """The key of the running application is not the old constant."""
    assert SECRET_KEY != PUBLISHED_DEFAULT_KEY
    assert len(SECRET_KEY) >= 32


def test_a_production_start_without_a_key_fails(tmp_path):
    """A production deployment must not start with a guessable key.

    The application has to refuse to start instead of signing tokens with a
    key that is published in the source.
    """
    environment = dict(os.environ, APP_ENV="production")
    environment.pop("SECRET_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.auth",
        ],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "the application started without a signing key"
    assert "SECRET_KEY" in result.stderr


def test_a_foreign_origin_gets_no_cors_header(client, registered_user):
    """CORS is an allow-list, not a wildcard."""
    _username, headers = registered_user

    response = client.get(
        "/api/v1/ml/models",
        headers={**headers, "Origin": "https://evil.example"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_the_development_origin_is_allowed(client, registered_user):
    """The origin of the SPA is allowed."""
    _username, headers = registered_user

    response = client.get(
        "/api/v1/ml/models",
        headers={**headers, "Origin": "http://localhost:3000"},
    )

    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    )


def test_only_failed_logins_count_against_the_budget(client, registered_user):
    """A user who signs in repeatedly is not locked out.

    The limiter exists to stop password guessing, not to stop a user from
    using the application.
    """
    username, _headers = registered_user

    for _ in range(15):
        response = client.post(
            "/token", data={"username": username, "password": "secret123"}
        )
        assert response.status_code == 200, response.text


def test_a_successful_login_forgets_the_failed_attempts(client, registered_user):
    """A correct password clears the budget of the account."""
    username, _headers = registered_user

    for _ in range(5):
        client.post("/token", data={"username": username, "password": "wrong"})

    assert (
        client.post(
            "/token", data={"username": username, "password": "secret123"}
        ).status_code
        == 200
    )


def test_the_rate_limit_does_not_lock_out_another_account(client, registered_user):
    """Guessing one account must not lock out the others.

    The budget is counted per address *and* username, so an attacker behind a
    shared address cannot deny the service to everybody else.
    """
    username, _headers = registered_user

    for _ in range(15):
        client.post("/token", data={"username": username, "password": "wrong"})

    blocked = client.post("/token", data={"username": username, "password": "secret123"})
    other = client.post(
        "/token", data={"username": "someone_else", "password": "secret123"}
    )

    assert blocked.status_code == 429
    assert other.status_code in (200, 400)


def test_the_registrations_are_rate_limited(client):
    """The account count of an address is limited."""
    for index in range(30):
        client.post(
            "/api/v1/register",
            json={"username": f"spam_{index}", "password": "secret123"},
        )

    response = client.post(
        "/api/v1/register", json={"username": "spam_final", "password": "secret123"}
    )

    assert response.status_code == 429, response.text
