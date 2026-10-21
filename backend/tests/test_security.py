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
from backend.app.main import LOGIN_RATE_LIMIT, app


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


def _key_in_a_fresh_process(environment=None, program="import app.auth; print(app.auth.SECRET_KEY)"):
    """The signing key of a process that starts with the given environment."""
    env = dict(os.environ, PYTHONPATH=BACKEND_DIR)
    env.pop("SECRET_KEY", None)
    if environment:
        env.update(environment)
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    return result


def test_the_development_key_is_not_the_published_default():
    """A process without SECRET_KEY must not sign with the old constant.

    The test suite sets SECRET_KEY for itself, so the key of the running
    application says nothing about the resolution: the check runs in a process
    that starts without the variable.
    """
    result = _key_in_a_fresh_process()

    assert result.returncode == 0, result.stderr
    key = result.stdout.strip().splitlines()[-1]
    assert key != PUBLISHED_DEFAULT_KEY
    assert len(key) >= 32


def test_the_development_key_is_stable_across_restarts():
    """The generated key is persisted, so the sessions survive a restart."""
    environment = {"SECRET_KEY_FILE": os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "week1-test-secret-key"
    )}
    try:
        first = _key_in_a_fresh_process(environment)
        second = _key_in_a_fresh_process(environment)
        assert first.returncode == 0, first.stderr
        assert second.returncode == 0, second.stderr
        assert first.stdout.strip().splitlines()[-1] == second.stdout.strip().splitlines()[-1]
    finally:
        path = environment["SECRET_KEY_FILE"]
        if os.path.exists(path):
            os.remove(path)


def test_a_production_start_without_a_key_fails(tmp_path):
    """A production deployment must not start with a guessable key.

    The application has to refuse to start instead of signing tokens with a
    key that is published in the source.
    """
    result = _key_in_a_fresh_process(
        {"APP_ENV": "production"},
        program="import app.auth",
    )

    assert result.returncode != 0, "the application started without a signing key"
    assert "SECRET_KEY" in result.stderr


def test_an_empty_app_env_does_not_disable_the_production_guard():
    """An empty APP_ENV must not fall back to the development key.

    A container that sets APP_ENV="" would otherwise run with a key that is
    generated on the spot - and every restart would invalidate the sessions.
    """
    result = _key_in_a_fresh_process(
        {"APP_ENV": "", "ENVIRONMENT": "production"},
        program="import app.auth",
    )

    assert result.returncode != 0, "the application started without a signing key"
    assert "SECRET_KEY" in result.stderr


def test_a_whitespace_secret_key_is_refused():
    """A key of spaces is not a key."""
    result = _key_in_a_fresh_process(
        {"SECRET_KEY": "   ", "APP_ENV": "production"},
        program="import app.auth",
    )

    assert result.returncode != 0, "a whitespace key was accepted"


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
    """A correct password clears the budget of the account.

    The budget is nearly exhausted first, so the assertion would fail if the
    successful login did not clear it: the failures after the success would
    run into the limit that was not reset.
    """
    username, _headers = registered_user

    for _ in range(LOGIN_RATE_LIMIT - 1):
        client.post("/token", data={"username": username, "password": "wrong"})

    assert (
        client.post(
            "/token", data={"username": username, "password": "secret123"}
        ).status_code
        == 200
    )

    # The budget was cleared by the success: the next failures are counted
    # from zero again, so the account is not blocked after the limit.
    for _ in range(LOGIN_RATE_LIMIT - 1):
        response = client.post(
            "/token", data={"username": username, "password": "wrong"}
        )
        assert response.status_code == 400, response.text


def test_a_locked_out_account_can_still_log_in_from_another_address(
    client, registered_user
):
    """An attacker must not be able to lock a victim out of their account.

    The budget of an account is counted per address, so the attempts of one
    client do not stop the victim from signing in.
    """
    username, _headers = registered_user

    for _ in range(LOGIN_RATE_LIMIT + 2):
        client.post("/token", data={"username": username, "password": "wrong"})

    blocked = client.post(
        "/token", data={"username": username, "password": "secret123"}
    )
    assert blocked.status_code == 429, "the attacker did not exhaust the budget"

    # A different client (a different address) is not affected.
    with TestClient(app, client=("198.51.100.7", 50000)) as other:
        other.post(
            "/api/v1/register", json={"username": username, "password": "secret123"}
        )
        response = other.post(
            "/token", data={"username": username, "password": "secret123"}
        )
        assert response.status_code == 200, response.text


def test_spraying_one_password_over_many_accounts_is_stopped(client, registered_user):
    """One client cannot try one password over many accounts.

    The address budget counts every failed login of the address, so the spray
    runs into the limit even though every account has its own budget.
    """
    for index in range(LOGIN_RATE_LIMIT * 4):
        client.post("/token", data={"username": f"sprayed_{index}", "password": "wrong"})

    response = client.post(
        "/token", data={"username": "sprayed_final", "password": "wrong"}
    )

    assert response.status_code == 429, response.text


def test_the_limiter_does_not_grow_without_bound(client):
    """An unauthenticated client must not be able to fill the memory.

    Every username of a request is a key of the limiter, so the entries of the
    clients that are not seen any more have to be forgotten.
    """
    from backend.app import main

    for index in range(200):
        client.post("/token", data={"username": f"memory_{index}", "password": "wrong"})

    assert len(main._login_attempts) <= main.RATE_LIMIT_MAX_CLIENTS


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


def _insert_user(username, hashed_password):
    """Insert a user row directly, the way an older database would have it."""
    import sqlite3

    from sqlalchemy.engine import make_url

    database_path = make_url(os.environ["DATABASE_URL"]).database
    connection = sqlite3.connect(database_path)
    try:
        with connection:
            connection.execute(
                "INSERT INTO users (username, hashed_password, role) VALUES (?, ?, 'user')",
                (username, hashed_password),
            )
    finally:
        connection.close()


def test_the_legacy_anonymous_account_cannot_log_in(client):
    """The shared account of the old fallback must not work any more.

    A database that predates the change still has the row, with the password
    ``anonymous``. The migration removes it, and the login refuses the
    reserved name as well - a row that was inserted by hand must not be a way
    in either.
    """
    from backend.app.auth import hash_pass

    _insert_user("anonymous", hash_pass("anonymous"))

    login = client.post(
        "/token", data={"username": "anonymous", "password": "anonymous"}
    )

    assert login.status_code == 400, login.text


def test_a_corrupt_password_hash_does_not_crash_the_login(client):
    """A row with a hash that is not a bcrypt hash answers 400, not 500."""
    _insert_user("corrupt_hash", "not-a-bcrypt-hash")

    login = client.post(
        "/token", data={"username": "corrupt_hash", "password": "secret123"}
    )

    assert login.status_code == 400, login.text


def test_a_password_of_multi_byte_characters_is_not_truncated(client):
    """A password is limited in bytes, not in characters.

    bcrypt hashes at most 72 bytes, so a password of multi-byte characters
    that is longer than 72 characters would be silently cut - and two
    different passwords would then be interchangeable.
    """
    password = "a" * 40 + "😀" * 20

    registration = client.post(
        "/api/v1/register", json={"username": "multibyte", "password": password}
    )

    assert registration.status_code == 400, registration.text


def test_the_openapi_document_describes_the_protected_endpoints():
    """The published API document says that the endpoints need a token.

    Without the security scheme, the Swagger UI has no "Authorize" button and
    the document describes the ML endpoints as if they were public.
    """
    schema = app.openapi()

    assert "OAuth2PasswordBearer" in str(schema.get("components", {}).get("securitySchemes", {}))
    protected = schema["paths"]["/api/v1/ml/models"]["get"]
    assert protected.get("security"), "the endpoint is documented as public"
