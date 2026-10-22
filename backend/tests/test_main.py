"""Tests for the routes of the API.

Every ML endpoint requires a token, so the tests register a user and send its
token. The training contract they check is the synchronous one; the phase that
makes the training asynchronous rewrites the two assertions that depend on the
metrics being in the response.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    """A TestClient that runs the lifespan (so the tables exist)."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    """The headers of a registered, logged-in user."""
    username = "routes_user"
    client.post(
        "/api/v1/register", json={"username": username, "password": "secret123"}
    )
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_ml_models(client, auth):
    response = client.get("/api/v1/ml/models", headers=auth)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_datasets(client, auth):
    response = client.get("/api/v1/ml/datasets", headers=auth)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert "datasets" in payload


def test_train_without_a_dataset_is_rejected(client, auth):
    """A training request needs a dataset.

    The dataset is a row of the registry, and the client never sends a path:
    a request without a dataset is a request that cannot be executed.
    """
    payload = {
        "model_name": "Logistic_Regression",
        "label_column": "label",
        "test_size": 0.2,
        "random_state": 42,
        "hyperparameters": {},
        "mode": "manual",
    }
    response = client.post("/api/v1/ml/train", headers=auth, json=payload)

    assert response.status_code == 400
    assert "dataset" in response.json()["detail"].lower()


def test_train_with_an_unknown_dataset_is_rejected(client, auth):
    """A dataset that does not exist is a 404, not a failed training."""
    payload = {
        "model_name": "Logistic_Regression",
        "dataset_name": "missing_dataset.csv",
        "label_column": "label",
        "test_size": 0.2,
        "random_state": 42,
        "hyperparameters": {},
        "mode": "manual",
    }
    response = client.post("/api/v1/ml/train", headers=auth, json=payload)

    assert response.status_code == 404
    assert "missing_dataset.csv" in response.json()["detail"]
