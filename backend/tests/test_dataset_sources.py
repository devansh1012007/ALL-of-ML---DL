"""The dataset sources of a training: the registry, Hugging Face and the environments.

A training does not always read a file of the datasets root: a request can name
a Hugging Face dataset, and a reinforcement learning model trains in an
environment and reads no data at all. These tests pin that the three sources
stay reachable - the registry is the only way to a *local* file, the other two
are not files of the server and must not be refused for the wrong reason.
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
    client.post(
        "/api/v1/register", json={"username": "sources_user", "password": "secret123"}
    )
    token = client.post(
        "/token", data={"username": "sources_user", "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_a_hugging_face_training_needs_no_local_dataset(client, auth, monkeypatch):
    """A request that names a Hugging Face dataset does not need a local one.

    Before, every request had to carry a dataset of the registry, so the
    Hugging Face mode of the form could only ever answer "either dataset_id or
    hf_dataset_url must be provided".
    """
    from backend.app import model_training

    def refuse(url):
        raise RuntimeError(f"the hugging face dataset {url} was reached")

    monkeypatch.setattr(model_training, "load_huggingface_dataset", refuse)

    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Logistic_Regression",
            "hf_dataset_url": "https://huggingface.co/datasets/some/one",
            "label_column": "label",
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    # The request reached the Hugging Face branch instead of being refused for
    # a missing dataset.
    assert "the hugging face dataset" in detail
    assert "dataset_id" not in detail


def test_a_reinforcement_learning_training_needs_no_dataset(client, auth, monkeypatch):
    """A reinforcement learning model trains in an environment, not on a file."""
    from backend.app import model_training

    monkeypatch.setattr(
        model_training,
        "_train_rl_model",
        lambda model_name, env_id, params: {"mean_reward": 12.5, "env_id": env_id},
    )

    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "PPO",
            "env_id": "CartPole-v1",
            "label_column": "label",
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["mean_reward"] == 12.5


def test_the_run_of_a_local_dataset_records_its_name(client, auth):
    """The run history shows the name of the dataset, not the path of the server.

    The path the registry resolved the row to is an internal detail: it holds
    the id of the owner and the name of the file on the disk.
    """
    listing = client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
    dataset = next(
        item for item in listing if item["name"] == "sample_customer_churn.csv"
    )

    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Logistic_Regression",
            "dataset_id": dataset["id"],
            "label_column": dataset["label_column"],
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
        },
    )
    assert response.status_code == 200, response.text

    runs = client.get("/api/v1/ml/runs", headers=auth).json()
    run = next(item for item in runs if item["id"] == response.json()["run_id"])
    assert run["dataset_tag"] == "sample_customer_churn.csv"
    assert "uploads/" not in run["dataset_tag"]
