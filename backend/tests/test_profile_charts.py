"""The dataset profile (plan C6) and the chart data (plan E1).

Looking at the data before training is what makes a notebook feel safe:
the profile answers what the columns hold, whether the label is balanced,
whether rows are duplicated or time-ordered, and - the part that catches
the most common wrong model - whether one feature alone predicts the label
(the leakage suspects). The chart data is what the run page draws, capped.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.charts import (
    build_classification_charts,
    build_regression_charts,
    cap_charts,
)
from backend.app.dataset_profile import compute_profile
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


# --- the profile (plan C6) --------------------------------------------------------


def _leaky_frame(n: int = 300, seed: int = 5) -> pd.DataFrame:
    """A frame with a planted leaking column (the label, slightly noised),
    an identifier-like column and a constant column."""
    rng = np.random.default_rng(seed)
    label = rng.integers(0, 2, n)
    return pd.DataFrame(
        {
            "row_id": np.arange(n),  # identifier-like: monotone, all distinct
            "noise_a": rng.normal(size=n),
            "noise_b": rng.normal(size=n),
            "the_leak": label + rng.normal(0, 0.01, n),  # the label itself
            "constant": np.ones(n),
            "label": label,
        }
    )


def test_the_profile_finds_the_planted_leaking_column(tmp_path):
    path = tmp_path / "leaky.csv"
    _leaky_frame().to_csv(path, index=False)

    profile = compute_profile(path, "label")

    suspects = profile["leakage_suspects"]
    assert suspects, "the planted leak was not detected"
    assert suspects[0]["column"] == "the_leak"
    assert suspects[0]["score"] >= 0.98


def test_the_profile_reports_the_identifier_and_the_constant_columns(tmp_path):
    path = tmp_path / "leaky.csv"
    _leaky_frame().to_csv(path, index=False)

    profile = compute_profile(path, "label")

    assert "row_id" in profile["constant_columns"] or "constant" in profile["constant_columns"]
    columns = {column["name"]: column for column in profile["columns"]}
    assert columns["row_id"].get("identifier_like") is True
    assert columns["the_leak"]["type"] == "numeric"
    assert "min" in columns["the_leak"] and "mean" in columns["the_leak"]


def test_the_profile_reports_the_label_distribution_and_the_duplicates(tmp_path):
    rng = np.random.default_rng(6)
    frame = pd.DataFrame(
        {
            "a": rng.normal(size=100),
            "b": rng.normal(size=100),
            "label": ["x"] * 90 + ["y"] * 10,  # imbalanced
        }
    )
    frame = pd.concat([frame, frame.head(10)])  # ten duplicate rows
    path = tmp_path / "imbalanced.csv"
    frame.to_csv(path, index=False)

    profile = compute_profile(path, "label")

    assert profile["label"]["classes"] == 2
    assert profile["label"]["imbalance_ratio"] == pytest.approx(10.0, rel=0.01)
    assert profile["duplicate_row_fraction"] > 0.05
    assert profile["label"]["missing_fraction"] == 0.0


def test_the_profile_hints_at_a_time_ordered_csv(tmp_path):
    rng = np.random.default_rng(7)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=200, freq="D").strftime("%Y-%m-%d"),
            "value": rng.normal(size=200).cumsum(),
        }
    )
    path = tmp_path / "series.csv"
    frame.to_csv(path, index=False)

    profile = compute_profile(path, "value")
    assert profile["rows_look_time_ordered"] is True


def test_the_profile_of_a_clean_frame_has_no_suspect(tmp_path):
    rng = np.random.default_rng(8)
    frame = pd.DataFrame(
        {
            "a": rng.normal(size=200),
            "b": rng.normal(size=200),
            "label": rng.integers(0, 2, 200),
        }
    )
    path = tmp_path / "clean.csv"
    frame.to_csv(path, index=False)

    profile = compute_profile(path, "label")
    assert profile["leakage_suspects"] == []


def test_the_profile_endpoint_answers_with_the_hash(client):
    """GET /datasets/{id}/profile: the data tab of plan C6, over HTTP."""
    auth = _login(client, "profile_user")
    listing = client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
    dataset = next(item for item in listing if item["name"] == "sample_customer_churn.csv")

    response = client.get(f"/api/v1/ml/datasets/{dataset['id']}/profile", headers=auth)
    assert response.status_code == 200, response.text
    profile = response.json()
    assert profile["rows"] > 0
    assert any(column["name"] == "churned" for column in profile["columns"])
    assert "label" in profile
    assert dataset["content_sha256"], "the dataset row carries its content hash"


# --- the chart data (plan E1) --------------------------------------------------------


def test_the_classification_charts_carry_the_curves():
    rng = np.random.default_rng(0)
    truth = rng.integers(0, 2, 200)
    scores = np.clip(truth * 0.8 + rng.normal(0.25, 0.15, 200), 0, 1)
    probabilities = np.stack([1 - scores, scores], axis=1)

    charts = build_classification_charts(
        truth, (scores > 0.5).astype(int), probabilities, class_labels=[0, 1]
    )

    assert "roc" in charts and len(charts["roc"]) >= 1
    assert "precision_recall" in charts
    assert "calibration" in charts
    assert "probability_histogram" in charts
    # The ROC curve is capped (plan E1: at most 200 points per curve).
    assert len(charts["roc"][0]["fpr"]) <= 200


def test_the_regression_charts_carry_the_errors():
    rng = np.random.default_rng(1)
    actual = rng.normal(size=300)
    predicted = actual + rng.normal(0, 0.1, 300)

    charts = build_regression_charts(actual, predicted)

    # The scatter is capped at 500 points (plan E1).
    assert len(charts["predicted_vs_actual"]["actual"]) <= 500
    assert len(charts["residual_histogram"]["counts"]) == 30
    assert len(charts["residuals_vs_predicted"]["residual"]) <= 500


def test_cap_charts_bounds_every_array():
    capped = cap_charts({"series": list(range(5000))})
    assert len(capped["series"]) <= 2000  # the safety net of the module


def test_a_run_stores_its_charts_outside_the_list(client):
    """The heavy data never leaves through the run list (plan E1): the list
    says has_charts, the dedicated endpoint serves it."""
    auth = _login(client, "charts_user")
    dataset = next(
        item
        for item in client.get("/api/v1/ml/datasets", headers=auth).json()["datasets"]
        if item["name"] == "sample_customer_churn.csv"
    )
    started = client.post(
        "/api/v1/ml/train",
        headers=auth,
        json={
            "model_name": "Random_Forest",
            "dataset_id": dataset["id"],
            "label_column": dataset["label_column"],
            "hyperparameters": {},
            "mode": "manual",
        },
    )
    assert started.status_code == 200, started.text

    # Wait for the run to finish, then inspect its chart data.
    import time

    run_id = started.json()["run_id"]
    deadline = time.monotonic() + 60
    while True:
        run = client.get(f"/api/v1/ml/runs/{run_id}", headers=auth).json()
        if run["status"] in ("completed", "failed", "cancelled"):
            break
        assert time.monotonic() < deadline, "the run did not finish"
        time.sleep(0.1)
    assert run["status"] == "completed", run
    assert run["has_charts"] is True

    listing = client.get("/api/v1/ml/runs", headers=auth).json()["items"]
    entry = next(item for item in listing if item["id"] == run_id)
    assert "charts" not in entry, "the run list must not carry the chart data"

    charts = client.get(f"/api/v1/ml/runs/{run_id}/charts", headers=auth)
    assert charts.status_code == 200
    body = charts.json()["charts"]
    # A classification run carries its importances (plan D5) and the fold
    # chart of its cross-validation (plan E1).
    assert "importances" in body or "roc" in body
