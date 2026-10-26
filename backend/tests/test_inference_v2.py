"""Inference, version 2 (plans D1 to D7).

A run is an experiment and never changes; a service needs an address that
survives retraining. These tests pin the parts a prediction service is made
of:

* **deployments (D1)**: a stable name, the one-transaction repointing, the
  event history, the rollback;
* **API keys (D2)**: predict-scoped, hashed, shown once, refused at once
  when revoked - and unable to reach anything but the predict endpoints;
* **batch from a file (D3)**: the synchronous CSV under the limit, the
  queued predict job above it, and the spreadsheet-injection defusing;
* **the dispatch (D4)**: a window for a forecaster, texts for a text model;
* **monitoring (D6)**: the hourly counters and the drift flag on a shifted
  sample.
"""

import io

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _login(client, username):
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def auth(client):
    return _login(client, "deploy_user")


@pytest.fixture()
def churn_run(client, auth, wait_for_run):
    dataset = next(
        item
        for item in client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
        if item["name"] == "sample_customer_churn.csv"
    )
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Random_Forest",
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
    return run


def _deploy(client, auth, run_id, name):
    created = client.post(
        "/api/v1/ml/deployments", headers=auth, json={"name": name, "run_id": run_id}
    )
    assert created.status_code == 200, created.text
    return created.json()


def _row(schema, **overrides):
    row = {feature["name"]: feature["default"] for feature in schema["features"]}
    row.update(overrides)
    return row


# --- the deployments (plan D1) ----------------------------------------------------


def test_a_completed_run_can_be_deployed_under_a_name(client, auth, churn_run):
    created = client.post(
        "/api/v1/ml/deployments",
        headers=auth,
        json={"name": "production", "run_id": churn_run["id"]},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "production"
    assert body["run_id"] == churn_run["id"]

    listed = client.get("/api/v1/ml/deployments", headers=auth).json()["items"]
    assert any(item["name"] == "production" for item in listed)


def test_the_schema_of_a_deployment_is_the_schema_of_its_run(client, auth, churn_run):
    _deploy(client, auth, churn_run["id"], "schema_check")
    schema = client.get("/api/v1/ml/deployments/schema_check/schema", headers=auth)
    assert schema.status_code == 200, schema.text
    assert schema.json()["run_id"] == churn_run["id"]
    assert schema.json()["request_kind"] == "rows"


def test_a_deployment_predicts_like_the_run(client, auth, churn_run):
    _deploy(client, auth, churn_run["id"], "predict_check")
    schema = client.get(
        f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=auth
    ).json()
    row = _row(schema)
    response = client.post(
        "/api/v1/ml/deployments/predict_check/predict",
        headers=auth,
        json={"rows": [row]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["predictions"]


def test_repointing_a_deployment_is_one_call_and_the_history_keeps_it(
    client, auth, churn_run, wait_for_run
):
    """Point the name at another run; the events keep where it pointed."""
    dataset = next(
        item
        for item in client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
        if item["name"] == "sample_customer_churn.csv"
    )
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "KNN",
            "dataset_id": dataset["id"],
            "label_column": dataset["label_column"],
            "hyperparameters": {},
            "mode": "manual",
        },
    )
    second = wait_for_run(client, auth, response.json()["run_id"])
    assert second["status"] == "completed", second

    _deploy(client, auth, churn_run["id"], "repoint_check")
    repointed = client.put(
        "/api/v1/ml/deployments/repoint_check",
        headers=auth,
        json={"name": "production", "run_id": second["id"]},
    )
    assert repointed.status_code == 200, repointed.text
    assert repointed.json()["run_id"] == second["id"]

    # The predict now goes through the new run.
    predicted = client.post(
        "/api/v1/ml/deployments/repoint_check/predict",
        headers=auth,
        json={"rows": [{"tenure_months": 1}]},
    )
    assert predicted.status_code == 200, predicted.text

    # Rolling back is pointing the name at the previous run.
    rolled = client.put(
        "/api/v1/ml/deployments/repoint_check",
        headers=auth,
        json={"name": "production", "run_id": churn_run["id"]},
    )
    assert rolled.status_code == 200
    assert rolled.json()["run_id"] == churn_run["id"]


def test_a_deployment_of_someone_else_is_not_found(client, churn_run):
    other = _login(client, "deploy_other_user")
    assert (
        client.get("/api/v1/ml/deployments/production/schema", headers=other).status_code
        == 404
    )


def test_a_deployment_needs_a_completed_run(client, auth):
    refused = client.post(
        "/api/v1/ml/deployments",
        headers=auth,
        json={"name": "broken", "run_id": 999999},
    )
    assert refused.status_code == 404


def test_a_deployment_can_be_deleted(client, auth, churn_run):
    """Deploy a run under a name, then remove it: the run itself is untouched."""
    _deploy(client, auth, churn_run["id"], "staging")
    deleted = client.delete("/api/v1/ml/deployments/staging", headers=auth)
    assert deleted.status_code == 200, deleted.text
    assert (
        client.get("/api/v1/ml/deployments/staging/schema", headers=auth).status_code
        == 404
    )
    # The run the name pointed at is still there.
    detail = client.get(f"/api/v1/ml/runs/{churn_run['id']}", headers=auth)
    assert detail.status_code == 200


# --- the API keys (plan D2) ------------------------------------------------------------


def test_an_api_key_predicts_and_cannot_do_anything_else(client, auth, churn_run):
    """The predict scope of plan D2: a leaked key can ask for predictions
    but cannot train, delete or read the owner's data."""
    created = client.post(
        "/api/v1/keys", headers=auth, json={"name": "ci", "expires_days": 7}
    )
    assert created.status_code == 200, created.text
    key = created.json()["key"]
    assert key.startswith("sk-")

    key_headers = {"Authorization": f"Bearer {key}"}
    # The key reaches the predict endpoints only (plan D2): the schema, the
    # runs, the keys - everything else needs the login.
    predicted = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict",
        headers=key_headers,
        json={"rows": [{"tenure_months": 3}]},
    )
    assert predicted.status_code == 200, predicted.text

    # Everything that is not a predict endpoint refuses the key.
    assert client.get("/api/v1/ml/runs", headers=key_headers).status_code == 401
    assert client.get("/api/v1/ml/models", headers=key_headers).status_code == 401
    assert client.get("/api/v1/keys", headers=key_headers).status_code == 401
    assert (
        client.post(
            "/api/v1/ml/train",
            headers=key_headers,
            json={"model_name": "KNN", "dataset_id": 1, "label_column": "x"},
        ).status_code
        == 401
    )

    # A revoked key stops working at the next request.
    key_id = created.json()["id"]
    assert (
        client.delete(f"/api/v1/keys/{key_id}", headers=auth).status_code == 200
    )
    refused = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict",
        headers=key_headers,
        json={"rows": [{"tenure_months": 3}]},
    )
    assert refused.status_code == 401
    assert "Invalid or revoked" in refused.json()["detail"]


def test_a_key_of_someone_else_is_not_found(client, auth):
    other = _login(client, "key_other_user")
    listed = client.get("/api/v1/keys", headers=other).json()["items"]
    assert listed == []


# --- the batch prediction from a file (plan D3) ------------------------------------------


def test_a_small_csv_is_answered_synchronously(client, auth, churn_run):
    schema = client.get(
        f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=auth
    ).json()
    buffer = io.StringIO()
    buffer.write(",".join(feature["name"] for feature in schema["features"]) + "\n")
    for index in range(5):
        buffer.write(
            ",".join(str(feature["default"]) for feature in schema["features"]) + "\n"
        )
    buffer.seek(0)

    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict-file",
        headers=auth,
        files={"file": ("rows.csv", buffer.getvalue(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert len(lines) == 6  # the header, the five predictions
    assert "prediction" in lines[0]


def test_a_csv_cell_a_spreadsheet_would_execute_is_defused(client, auth, churn_run):
    """A downloaded CSV must not carry a formula (plan G3).

    The dangerous cell has to sit in a categorical column: a numeric one is
    refused by the coercion (correctly, with a 422 that names the column),
    a categorical one passes through as an unknown category - and the
    answer CSV must carry it defused.
    """
    schema = client.get(
        f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=auth
    ).json()
    categorical = next(
        (f["name"] for f in schema["features"] if f["kind"] == "categorical"), None
    )
    if categorical is None:
        pytest.skip("the model has no categorical feature to carry the formula")
    columns = [f["name"] for f in schema["features"]]
    row = {f["name"]: f["default"] for f in schema["features"]}
    row[categorical] = "=CMD()"
    buffer = io.StringIO()
    buffer.write(",".join(columns) + "\n")
    buffer.write(",".join(str(row[name]) for name in columns) + "\n")
    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict-file",
        headers=auth,
        files={"file": ("rows.csv", buffer.getvalue(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert "'=CMD()" in response.text


def test_a_large_csv_becomes_a_queued_predict_job(client, auth, churn_run, monkeypatch):
    from backend.app import inference

    monkeypatch.setattr(inference, "BATCH_SYNC_MAX_ROWS", 2)
    schema = client.get(
        f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=auth
    ).json()
    columns = [feature["name"] for feature in schema["features"]]
    buffer = io.StringIO()
    buffer.write(",".join(columns) + "\n")
    for _ in range(3):
        buffer.write(",".join(str(feature["default"]) for feature in schema["features"]) + "\n")

    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict-file",
        headers=auth,
        files={"file": ("rows.csv", buffer.getvalue(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert "job_run_id" in body

    job = client.get(f"/api/v1/ml/runs/{body['job_run_id']}", headers=auth).json()
    assert job["job_kind"] == "predict"


# --- the monitoring counters (plan D6) ------------------------------------------------------


def test_the_deployment_stats_count_the_requests_and_flag_drift(client, auth, churn_run):
    _deploy(client, auth, churn_run["id"], "stats_check")
    schema = client.get(
        f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=auth
    ).json()
    # A request through the deployment: the counters of the hour grow.
    client.post(
        "/api/v1/ml/deployments/stats_check/predict",
        headers=auth,
        json={"rows": [_row(schema)] * 3},
    )
    stats = client.get("/api/v1/ml/deployments/stats_check/stats", headers=auth)
    assert stats.status_code == 200, stats.text
    hours = stats.json()["hours"]
    assert hours and hours[-1]["requests"] >= 1
    assert hours[-1]["rows"] >= 3


# --- the dispatch on the bundle kind (plan D4) ------------------------------------------------


def test_a_forecaster_predicts_from_a_window(client, wait_for_run):
    """A time-series run answers with the next horizon values from the last
    window rows (plans F3, D4)."""
    owner = _login(client, "forecast_user")
    datasets = client.get("/api/v1/ml/datasets", headers=owner).json()["datasets"]
    # The sine series of plan F1, generated into the datasets root by the
    # test below it if the sample is not there yet.
    import numpy as np
    import pandas as pd

    from backend.app.settings import datasets_root

    root = datasets_root()
    sine_path = root / "data" / "synthetic_sine.csv"
    if not sine_path.exists():
        series = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=120).strftime("%Y-%m-%d"),
                "value": (np.sin(np.arange(120) * 2 * np.pi / 24) * 3).round(4),
            }
        )
        sine_path.parent.mkdir(parents=True, exist_ok=True)
        series.to_csv(sine_path, index=False)
    dataset = next(
        (item for item in datasets if item["name"] == "synthetic_sine.csv"), None
    )
    if dataset is None:
        pytest.skip("the sine dataset was not registered by the startup")

    response = client.post(
        "/api/v1/ml/train",
        headers=owner,
        json={
            "model_name": "LSTM",
            "dataset_id": dataset["id"],
            "label_column": "value",
            "hyperparameters": {"window": 12, "horizon": 2, "epochs": 2},
            "mode": "manual",
        },
    )
    assert response.status_code == 200, response.text
    run = wait_for_run(client, owner, response.json()["run_id"])
    assert run["status"] == "completed", run
    assert run["metrics"]["task_type"] == "timeseries"
    assert run["metrics"]["baseline_naive_mae"] is not None

    schema = client.get(f"/api/v1/ml/runs/{run['id']}/schema", headers=owner).json()
    assert schema["request_kind"] == "window_rows"
    window = [[float(value)] for value in range(schema["window"])]
    predicted = client.post(
        f"/api/v1/ml/runs/{run['id']}/predict",
        headers=owner,
        json={"window_rows": window},
    )
    assert predicted.status_code == 200, predicted.text
    assert len(predicted.json()["predictions"]) == schema["horizon"]


def test_a_clustering_model_without_a_predict_step_says_so(client, auth, wait_for_run):
    """t-SNE describes the rows it was fitted on: the endpoint answers with
    the reason instead of guessing (plans C2, D4)."""
    dataset = next(
        item
        for item in client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
        if item["name"] == "sample_customer_churn.csv"
    )
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "t-SNE",
            "dataset_id": dataset["id"],
            "label_column": "churned",
            "hyperparameters": {"perplexity": 5},
            "mode": "manual",
        },
    )
    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "completed", run

    schema = client.get(f"/api/v1/ml/runs/{run['id']}/schema", headers=auth)
    assert schema.status_code == 200
    assert schema.json()["can_predict"] is False

    predicted = client.post(
        f"/api/v1/ml/runs/{run['id']}/predict",
        headers=auth,
        json={"rows": [{"tenure_months": 1}]},
    )
    assert predicted.status_code == 422
    assert "cannot assign new rows" in predicted.json()["detail"]
