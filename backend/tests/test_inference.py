"""The inference endpoints: a saved artifact becomes a prediction service.

``GET /runs/{id}/schema`` says which columns a model expects, and
``POST /runs/{id}/predict`` answers for rows it has never seen. These tests
pin the contract end to end (train through the API, wait, ask for predictions)
and the ways the endpoints refuse a request:

* only the owner of a run can use it, and only a completed one;
* a row the model cannot use is a 422 that names the column;
* an artifact that is not a bundle (a run from before the change) is refused
  with an explanation instead of a crash;
* an artifact outside the model directory is never unpickled.
"""

import joblib
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
    return _login(client, "inference_user")


@pytest.fixture(scope="module")
def other_auth(client):
    return _login(client, "inference_other_user")


def _dataset(client, auth, name):
    listing = client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
    return next(item for item in listing if item["name"] == name)


def _train(client, auth, wait_for_run, model_name, dataset_name, **extra):
    dataset = _dataset(client, auth, dataset_name)
    response = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": model_name,
            "dataset_id": dataset["id"],
            "label_column": dataset["label_column"],
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
            **extra,
        },
    )
    assert response.status_code == 200, response.text
    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "completed", run
    return run


@pytest.fixture
def churn_run(client, auth, wait_for_run):
    return _train(client, auth, wait_for_run, "Random_Forest", "sample_customer_churn.csv")


def test_the_run_says_that_it_can_predict(churn_run):
    assert churn_run["metrics"]["artifact_kind"] == "tabular"


def test_the_schema_lists_the_columns_of_the_model(client, auth, churn_run):
    response = client.get(f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=auth)

    assert response.status_code == 200, response.text
    schema = response.json()
    assert schema["task_type"] == "classification"
    assert schema["label_column"] == "churned"
    names = [feature["name"] for feature in schema["features"]]
    assert names == [
        "tenure_months",
        "monthly_charges",
        "support_tickets",
        "plan_tier",
        "satisfaction_score",
    ]
    tenure = schema["features"][0]
    assert tenure["kind"] == "numeric"
    assert tenure["min"] <= tenure["default"] <= tenure["max"]
    assert schema["classes"] == [0, 1]
    assert schema["max_rows"] >= 1


def test_predict_answers_for_rows_built_from_the_schema_defaults(client, auth, churn_run):
    schema = client.get(f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=auth).json()
    row = {feature["name"]: feature["default"] for feature in schema["features"]}

    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict",
        headers=auth,
        json={"rows": [row, {**row, "tenure_months": 1}]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["n_rows"] == 2
    assert body["model_name"] == "Random_Forest"
    assert body["classes"] == [0, 1]
    assert len(body["predictions"]) == 2
    assert set(body["predictions"]) <= {0, 1}
    for probabilities in body["probabilities"]:
        assert sum(probabilities.values()) == pytest.approx(1.0)
    assert body["warnings"] == []


def test_the_prediction_matches_what_the_artifact_gives_directly(
    client, auth, churn_run
):
    """The endpoint adds no logic of its own: it is the bundle, over HTTP."""
    bundle = joblib.load(churn_run["artifact_path"].rstrip("/") + "/model.joblib")
    bundle = __import__("backend.app.bundles", fromlist=["load_any_artifact"]).load_any_artifact(
        __import__("pathlib").Path(churn_run["artifact_path"])
    )
    row = {
        "tenure_months": 2,
        "monthly_charges": 95.0,
        "support_tickets": 6,
        "plan_tier": 1,
        "satisfaction_score": 2.0,
    }

    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict", headers=auth, json={"rows": [row]}
    )

    assert response.json()["predictions"] == bundle.infer([row])["predictions"]


def test_a_regression_run_predicts_numbers(client, auth, wait_for_run):
    run = _train(client, auth, wait_for_run, "Random_Forest", "sample_house_prices.csv")
    schema = client.get(f"/api/v1/ml/runs/{run['id']}/schema", headers=auth).json()
    row = {f["name"]: f["default"] for f in schema["features"]}

    response = client.post(
        f"/api/v1/ml/runs/{run['id']}/predict", headers=auth, json={"rows": [row]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["task_type"] == "regression"
    assert isinstance(body["predictions"][0], float)
    assert "probabilities" not in body


def test_a_missing_or_unknown_column_is_a_warning_not_an_error(client, auth, churn_run):
    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict",
        headers=auth,
        json={"rows": [{"tenure_months": 5, "shoe_size": 42}]},
    )

    assert response.status_code == 200, response.text
    text = " ".join(response.json()["warnings"])
    assert "shoe_size" in text and "monthly_charges" in text


def test_a_value_that_is_not_a_number_is_a_422_that_names_the_column(client, auth, churn_run):
    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict",
        headers=auth,
        json={"rows": [{"tenure_months": "a long time"}]},
    )

    assert response.status_code == 422
    assert "tenure_months" in response.json()["detail"]


def test_an_empty_request_is_refused(client, auth, churn_run):
    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict", headers=auth, json={"rows": []}
    )
    assert response.status_code == 422


def test_a_request_with_too_many_rows_is_refused(client, auth, churn_run, monkeypatch):
    from backend.app import main

    monkeypatch.setattr(main, "PREDICT_MAX_ROWS", 2)

    response = client.post(
        f"/api/v1/ml/runs/{churn_run['id']}/predict",
        headers=auth,
        json={"rows": [{"tenure_months": 1}] * 3},
    )

    assert response.status_code == 413
    assert "at most 2" in response.json()["detail"]


def test_a_run_of_someone_else_is_not_found(client, other_auth, churn_run):
    for call in (
        lambda: client.get(f"/api/v1/ml/runs/{churn_run['id']}/schema", headers=other_auth),
        lambda: client.post(
            f"/api/v1/ml/runs/{churn_run['id']}/predict",
            headers=other_auth,
            json={"rows": [{"tenure_months": 1}]},
        ),
    ):
        assert call().status_code == 404


def test_the_endpoints_need_a_token(client, churn_run):
    assert client.get(f"/api/v1/ml/runs/{churn_run['id']}/schema").status_code == 401
    assert (
        client.post(
            f"/api/v1/ml/runs/{churn_run['id']}/predict", json={"rows": [{"a": 1}]}
        ).status_code
        == 401
    )


def test_a_run_that_did_not_complete_cannot_predict(client, auth, wait_for_run, monkeypatch):
    from backend.app import main

    def refuse(*args, **kwargs):
        raise ValueError("the model could not be trained")

    monkeypatch.setattr(main, "train_model", refuse)
    dataset = _dataset(client, auth, "sample_customer_churn.csv")
    started = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Random_Forest",
            "dataset_id": dataset["id"],
            "label_column": dataset["label_column"],
        },
    ).json()
    failed = wait_for_run(client, auth, started["run_id"])
    assert failed["status"] == "failed"

    response = client.post(
        f"/api/v1/ml/runs/{failed['id']}/predict", headers=auth, json={"rows": [{"a": 1}]}
    )

    assert response.status_code == 409
    assert "failed" in response.json()["detail"]


def _point_the_run_at(run_id, artifact_path):
    import sqlite3

    from sqlalchemy.engine import make_url

    from backend.app.database import DATABASE_URL

    connection = sqlite3.connect(make_url(DATABASE_URL).database)
    try:
        connection.execute(
            "UPDATE training_runs SET artifact_path = ?, artifact_sha256 = NULL WHERE id = ?",
            (str(artifact_path), run_id),
        )
        connection.commit()
    finally:
        connection.close()


def test_an_artifact_that_is_not_a_bundle_is_refused_with_an_explanation(
    client, auth, wait_for_run, isolated_model_dir
):
    """A run from before the change saved a bare estimator: it cannot predict."""
    from sklearn.linear_model import LogisticRegression

    run = _train(client, auth, wait_for_run, "Logistic_Regression", "sample_customer_churn.csv")
    legacy = isolated_model_dir / "legacy_model.joblib"
    joblib.dump(LogisticRegression(), legacy)
    _point_the_run_at(run["id"], legacy)

    response = client.post(
        f"/api/v1/ml/runs/{run['id']}/predict", headers=auth, json={"rows": [{"a": 1}]}
    )

    assert response.status_code == 422
    assert "cannot predict" in response.json()["detail"]
    assert "trained again" in response.json()["detail"]


def test_an_artifact_outside_the_model_directory_is_never_loaded(
    client, auth, wait_for_run, tmp_path_factory
):
    """Loading an artifact unpickles it, which runs code: the path is checked first."""
    run = _train(client, auth, wait_for_run, "Logistic_Regression", "sample_customer_churn.csv")
    outside = tmp_path_factory.mktemp("elsewhere") / "evil.joblib"
    joblib.dump({"not": "a model"}, outside)
    _point_the_run_at(run["id"], outside)

    response = client.post(
        f"/api/v1/ml/runs/{run['id']}/predict", headers=auth, json={"rows": [{"a": 1}]}
    )

    assert response.status_code == 404


def test_an_autoencoder_run_scores_rows_by_how_unusual_they_are(client, auth, wait_for_run):
    run = _train(client, auth, wait_for_run, "Autoencoder", "sample_customer_churn.csv")
    assert run["metrics"]["artifact_kind"] == "autoencoder"
    schema = client.get(f"/api/v1/ml/runs/{run['id']}/schema", headers=auth).json()
    # The label of the file is not a feature of an unsupervised model.
    assert schema["kind"] == "autoencoder"
    assert "churned" not in [f["name"] for f in schema["features"]]
    usual = {f["name"]: f["default"] for f in schema["features"]}
    odd = {**usual, "tenure_months": 5000, "monthly_charges": -900.0}

    response = client.post(
        f"/api/v1/ml/runs/{run['id']}/predict", headers=auth, json={"rows": [usual, odd]}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    usual_error, odd_error = body["reconstruction_error"]
    assert odd_error > usual_error
    assert body["is_anomaly"][1] is True
    assert len(body["latent"]) == 2 and len(body["latent"][0]) == run["metrics"]["latent_dim"]
