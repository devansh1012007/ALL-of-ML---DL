"""The asynchronous contract of the training.

The training does not run inside the request any more: the request answers
immediately with the id of the run, and the result is read from the run
itself. These tests pin that contract:

* the answer carries the id of the run and no metrics;
* the row exists before the answer, so that the client can poll it;
* a training that works reaches `completed` with its metrics and its
  artifact;
* a training that fails reaches `failed` with the error in the run - the run
  is the only channel the client has left;
* a run that a restart interrupted is failed at the next start;
* two runs that start in the same second get two different artifacts.
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
        "/api/v1/register", json={"username": "async_user", "password": "secret123"}
    )
    token = client.post(
        "/token", data={"username": "async_user", "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _the_sample_dataset(client, auth):
    listing = client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
    return next(
        item for item in listing if item["name"] == "sample_customer_churn.csv"
    )


def test_the_answer_carries_the_id_of_the_run_and_no_metrics(client, auth):
    """The request answers immediately: the result is not in the answer."""
    dataset = _the_sample_dataset(client, auth)

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
    payload = response.json()
    assert isinstance(payload["run_id"], int)
    assert payload["status"] in ("queued", "running", "completed")
    assert payload["metrics"] is None
    assert payload["artifact_path"] is None


def test_the_row_exists_before_the_answer(client, auth):
    """The client polls the run, so the row has to exist when it answers.

    A client that polls an id the database does not know yet would get a 404
    and would give up.
    """
    dataset = _the_sample_dataset(client, auth)

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

    run = client.get(
        f"/api/v1/ml/runs/{response.json()['run_id']}", headers=auth
    )
    assert run.status_code == 200, run.text


def test_a_training_that_works_reaches_completed(client, auth, wait_for_run):
    """The metrics and the artifact are written in the run."""
    dataset = _the_sample_dataset(client, auth)

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

    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "completed", run
    assert run["metrics"]["accuracy"] > 0.5
    assert run["artifact_path"]
    assert run["dataset_source"] == "local"


def test_a_training_that_fails_reaches_failed(client, auth, wait_for_run, monkeypatch):
    """The run is the channel of the error: the request was answered long ago."""
    from backend.app import main

    def refuse(*args, **kwargs):
        raise ValueError("the model could not be trained")

    # The endpoint holds its own reference to train_model, so the patch is
    # made where the endpoint looks it up.
    monkeypatch.setattr(main, "train_model", refuse)
    dataset = _the_sample_dataset(client, auth)

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
    # The request is accepted: the failure happens in the background.
    assert response.status_code == 200, response.text

    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "failed", run
    assert "could not be trained" in run["metrics"]["error"]


def test_the_error_of_a_run_holds_no_path_of_the_server(
    client, auth, wait_for_run, monkeypatch
):
    """The error of a run is read by the owner, and it holds no path.

    The text of an exception carries the internals of the server: the
    directory of the datasets and the directory of the artifacts are replaced
    by a marker.
    """
    from backend.app import main
    from backend.app.model_training import MODEL_DIR

    def refuse(*args, **kwargs):
        raise ValueError(f"the file {MODEL_DIR}/model.joblib could not be read")

    monkeypatch.setattr(main, "train_model", refuse)
    dataset = _the_sample_dataset(client, auth)

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

    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "failed", run
    error = run["metrics"]["error"]
    assert str(MODEL_DIR) not in error
    assert "<server>" in error
    # The reason of the failure survives: the client has to be able to act.
    assert "could not be read" in error


def test_a_run_that_a_restart_interrupted_is_failed_at_the_next_start(client, auth):
    """A run that was running when the process died is failed.

    The worker that owned it died with the process: the run would stay in a
    state that never changes otherwise.
    """
    import asyncio

    from backend.app.main import reap_the_interrupted_runs
    from backend.app.models import TrainingRun
    from backend.app.database import AsyncSessionLocal

    async def leave_a_run_running():
        async with AsyncSessionLocal() as session:
            run = TrainingRun(
                owner_id=1,
                model_name="Logistic_Regression",
                dataset_source="local",
                dataset_tag="sample_customer_churn.csv",
                hyperparameters={},
                mode="manual",
                status="running",
            )
            session.add(run)
            await session.commit()
            return run.id

    run_id = asyncio.run(leave_a_run_running())

    asyncio.run(reap_the_interrupted_runs())

    response = client.get(f"/api/v1/ml/runs/{run_id}", headers=auth)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "failed", run
    assert "restarted" in run["metrics"]["error"].lower()


def test_two_runs_in_the_same_second_get_different_artifacts(client, auth, wait_for_run):
    """The artifact of a run is written with a name of its own.

    Two runs that start in the same second would write over each other's
    artifact otherwise.
    """
    dataset = _the_sample_dataset(client, auth)
    payload = {
        "model_name": "Logistic_Regression",
        "dataset_id": dataset["id"],
        "label_column": dataset["label_column"],
        "test_size": 0.2,
        "random_state": 42,
        "hyperparameters": {},
        "mode": "manual",
    }

    first = client.post("/api/v1/ml/train", headers=auth, json=payload)
    second = client.post("/api/v1/ml/train", headers=auth, json=payload)
    assert first.status_code == 200 and second.status_code == 200

    first_run = wait_for_run(client, auth, first.json()["run_id"])
    second_run = wait_for_run(client, auth, second.json()["run_id"])

    assert first_run["artifact_path"] != second_run["artifact_path"]
    assert first_run["artifact_path"]
    assert second_run["artifact_path"]
