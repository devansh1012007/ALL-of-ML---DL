"""Observability (plan H3): health, readiness, metrics, request logs.

The three endpoints answer the operator's questions without a database
shell: is the process up, is the schema at the right revision, and what is
the queue doing. The request log carries a request id the client can echo
and a run id when the path has one.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import observability
from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    username = "obs_user"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_healthz_says_ok_when_the_database_answers(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_reports_the_migration_revision(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["revision"], "the revision the schema is at"


def test_metrics_renders_the_prometheus_format(client, auth):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    for counter in (
        "# HELP ml_queue_depth",
        "# TYPE ml_queue_depth gauge",
        'ml_queue_depth{status="queued"}',
        "ml_run_seconds_sum",
        "ml_run_seconds_count",
        "# HELP ml_run_failures_total",
        "ml_predict_requests_total",
        "ml_live_workers",
    ):
        assert counter in body, f"missing {counter} in the metrics"


def test_the_metrics_content_type_is_the_prometheus_one(client):
    response = client.get("/metrics")
    assert "version=0.0.4" in response.headers["content-type"]


def test_the_predict_latency_ring_records_a_value():
    # The ring is shared by the process: the executor tests may have fed it.
    observability._PREDICT_LATENCIES.clear()
    observability.record_predict_latency(0.25)
    observability.record_predict_latency(0.75)
    summary = observability._latency_summary()
    assert summary["count"] == 2
    assert summary["p50"] == 0.25
    assert summary["p95"] == 0.75


def test_the_request_id_is_echoed_back(client):
    response = client.get("/healthz", headers={"X-Request-ID": "my-own-id-42"})
    assert response.headers.get("x-request-id") == "my-own-id-42"


def test_a_request_without_an_id_gets_one(client):
    response = client.get("/healthz")
    assert response.headers.get("x-request-id")
    assert response.headers["x-request-id"] != "my-own-id-42"


class _InfoSpy:
    """Watch the calls the middleware makes to its logger.

    The middleware's contract is the JSON payload it hands to ``info``; the
    delivery of a record to a handler is the standard library's business and
    is exercised by every other consumer of the logger.
    """

    def __init__(self):
        self.messages = []

    def __call__(self, message, *args, **kwargs):
        self.messages.append(message)


@pytest.fixture
def request_log():
    spy = _InfoSpy()
    target = logging.getLogger("observability")
    original = target.info
    target.info = spy
    yield spy.messages
    target.info = original


def test_the_request_log_carries_the_request_and_the_run_id(client, auth, request_log):
    """One JSON line per request, with the ids the operator greps for."""
    client.get("/api/v1/ml/runs?limit=1", headers=auth)
    assert request_log, "the request was not logged"
    entry = json.loads(request_log[-1])
    assert entry["request_id"]
    assert entry["run_id"] is None  # the list path carries no run id
    assert entry["path"] == "/api/v1/ml/runs"
    assert entry["status"] == 200
    assert "duration_ms" in entry


def test_a_run_path_puts_the_run_id_in_the_log(client, auth, request_log):
    client.get("/api/v1/ml/runs/999999", headers=auth)
    assert request_log, "the request was not logged"
    entry = json.loads(request_log[-1])
    assert entry["run_id"] == "999999"


def test_the_health_endpoints_are_not_logged_by_default(client, request_log):
    """A scraper polling /metrics every second must not fill the log."""
    client.get("/healthz")
    client.get("/readyz")
    client.get("/metrics")
    assert request_log == []
