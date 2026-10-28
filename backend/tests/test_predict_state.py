"""A reinforcement-learning model can be asked what to do.

The Q-table and policy bundles declare ``request_kind = "state"`` and answer
``infer({"state": ...})``, but the endpoint had no ``state`` field and no branch
for it: a trained agent could never be queried (it fell into "the endpoint does
not build this request"). These tests go through the real HTTP route, which is
the path that was broken and the one a user takes.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    client.post("/api/v1/register", json={"username": "state_user", "password": "secret123"})
    token = client.post(
        "/token", data={"username": "state_user", "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def q_run(client, auth, wait_for_run):
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Q-Learning",
            "env_id": "FrozenLake-v1",
            "label_column": "label",
            "hyperparameters": {"training_steps": 2000},
            "mode": "manual",
        },
    )
    assert response.status_code == 200, response.text
    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "completed", run
    return run


def _predict(client, auth, run, body):
    return client.post(f"/api/v1/ml/runs/{run['id']}/predict", headers=auth, json=body)


def test_a_q_table_answers_with_an_action_and_the_values_behind_it(client, auth, q_run):
    response = _predict(client, auth, q_run, {"state": 0})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_kind"] == "state"
    assert body["action"] in (0, 1, 2, 3)  # FrozenLake has four moves
    assert len(body["q_values"]) == 4
    # The action is the best value of the table: the answer explains itself.
    assert body["q_values"][body["action"]] == max(body["q_values"])


def test_a_request_without_a_state_says_what_to_send(client, auth, q_run):
    response = _predict(client, auth, q_run, {})

    assert response.status_code == 422
    assert "state" in response.json()["detail"]


def test_a_state_outside_the_table_names_the_valid_range(client, auth, q_run):
    response = _predict(client, auth, q_run, {"state": 999})

    assert response.status_code == 422
    assert "between 0 and 15" in response.json()["detail"]
