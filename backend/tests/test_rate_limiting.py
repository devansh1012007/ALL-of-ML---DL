"""The rate limiter of plan A8: shared, proxy-aware, keyed on the caller.

The limiter used to live in the memory of one process. The properties that
are pinned here are the reason it moved:

* the budget is in the database, so two "processes" (two sessions) see the
  same count - the property the in-memory limiter could not deliver;
* the address of the client comes from ``X-Forwarded-For`` only when the
  socket address is a trusted proxy, and the walk starts from the right;
* an upload is budgeted per *user*, not per address;
* the ledger does not grow without bound: the purge removes what fell out
  of every window.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.app import main, rate_limit
from backend.app.main import (
    LOGIN_RATE_LIMIT,
    REGISTER_RATE_LIMIT,
    UPLOAD_RATE_LIMIT,
    app,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _session_count(key: str) -> int:
    """The count a *second* connection sees: the proof the budget is shared."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.settings import DATABASE_URL

    async def _one():
        engine = create_async_engine(DATABASE_URL)
        factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                return await rate_limit.count_events(session, key, main.RATE_LIMIT_WINDOW_SECONDS)
        finally:
            await engine.dispose()

    return asyncio.run(_one())


def test_the_budget_is_shared_by_two_connections(client):
    """A failed login recorded by one session is visible to another.

    This is the property the in-memory limiter could not deliver: a second
    worker would have had its own, fresh budget.
    """
    key = "login:testclient:spray_shared"
    for _ in range(3):
        client.post("/token", data={"username": "nobody_here", "password": "wrong"})

    seen = _session_count(f"login:testclient:nobody_here")
    assert seen >= 1


def test_a_failed_login_counts_once_per_key(client):
    """The account key and the address key are two budgets; a failed login
    writes one event into each."""
    client.post("/token", data={"username": "double_key", "password": "wrong"})
    assert _session_count("login:testclient:double_key") == 1
    assert _session_count("login-address:testclient") >= 1


def test_the_window_frees_the_budget(client, monkeypatch):
    """Events that fall out of the window no longer count."""
    # A window of zero: every event is already too old when the next request
    # checks the count.
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_WINDOW_SECONDS", 0.0)
    monkeypatch.setattr(main, "RATE_LIMIT_WINDOW_SECONDS", 0.0)
    for index in range(LOGIN_RATE_LIMIT + 2):
        response = client.post(
            "/token", data={"username": "window_user", "password": "wrong"}
        )
        if index < LOGIN_RATE_LIMIT:
            assert response.status_code == 400
    # With a zero window nothing accumulates, so the last attempt is a plain
    # wrong-password 400 and not a 429.
    response = client.post(
        "/token", data={"username": "window_user", "password": "wrong"}
    )
    assert response.status_code == 400


def test_the_trusted_proxy_is_the_only_way_to_believe_xff(client, monkeypatch):
    """A forged X-Forwarded-For is ignored unless the socket is a trusted
    proxy; with trust declared, the rightmost non-trusted hop wins."""
    from fastapi import Request as _Request

    scope = {
        "type": "http",
        "client": ("10.0.0.5", 50000),
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 10.0.0.9")],
    }
    request = _Request(scope)

    monkeypatch.setattr(main, "TRUSTED_PROXIES", set())
    assert main._client_address(request) == "10.0.0.5"

    monkeypatch.setattr(main, "TRUSTED_PROXIES", {"10.0.0.5"})
    # The rightmost hop that nobody vouched for is the client; 1.2.3.4 is
    # whatever the attacker wrote in the left of the list.
    assert main._client_address(request) == "10.0.0.9"

    # A chain of trusted proxies: keep walking to the left.
    monkeypatch.setattr(main, "TRUSTED_PROXIES", {"10.0.0.5", "10.0.0.9"})
    assert main._client_address(request) == "1.2.3.4"


def test_the_upload_budget_is_per_user(client):
    """Two uploads of one user count against one key that names the user."""
    client.post("/api/v1/register", json={"username": "up_limit", "password": "secret123"})
    token = client.post(
        "/token", data={"username": "up_limit", "password": "secret123"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    content = b"a,b\n1,2\n"

    response = client.post(
        "/api/v1/ml/datasets/upload",
        files={"file": ("small.csv", content, "text/csv")},
        headers=headers,
    )
    assert response.status_code in (200, 201), response.text
    assert _session_count(f"upload:user:{response.json()['id'] and _user_id(client, headers)}") >= 1


def _user_id(client, headers):
    return client.get("/api/v1/me", headers=headers).json()["id"]


def test_the_purge_removes_what_fell_out_of_every_window(client):
    for _ in range(3):
        client.post("/token", data={"username": "purge_me", "password": "wrong"})
    assert _session_count("login:testclient:purge_me") == 3
    # Everything older than "now" is gone.
    rate_limit.purge_rate_events_on_engine(older_than_seconds=0.0)
    assert _session_count("login:testclient:purge_me") == 0
