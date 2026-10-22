"""Tests for the dataset registry.

The registry is the boundary between the client and the filesystem: a dataset
is a row, the client refers to it by its id, and the server decides which file
that id means. These tests pin that contract:

* an upload is stored, registered and usable;
* a dataset of another user cannot be seen or trained on;
* a path that leaves the datasets root is refused - the primitive that let a
  client read any file of the server is gone;
* the built-in datasets of the repository are registered at startup.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.datasets import (
    DatasetError,
    describe_csv,
    resolve_storage_path,
    store_upload,
    suggest_label,
)
from backend.app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_CONTENT = "feature_a,feature_b,label\n1,2,0\n3,4,1\n5,6,0\n7,8,1\n"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    """The headers of a registered, logged-in user."""
    client.post(
        "/api/v1/register", json={"username": "datasets_user", "password": "secret123"}
    )
    token = client.post(
        "/token", data={"username": "datasets_user", "password": "secret123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_an_upload_is_stored_and_registered(client, auth):
    """An uploaded file becomes a dataset the user can train on."""
    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("churn.csv", CSV_CONTENT.encode(), "text/csv")},
    )

    assert response.status_code == 200, response.text
    dataset = response.json()
    assert dataset["name"] == "churn.csv"
    assert dataset["source"] == "upload"
    assert dataset["row_count"] == 4
    assert [column["name"] for column in dataset["columns"]] == [
        "feature_a",
        "feature_b",
        "label",
    ]
    assert dataset["label_column"] == "label"

    listing = client.get("/api/v1/ml/datasets", headers=auth)
    assert listing.status_code == 200
    assert dataset["id"] in [item["id"] for item in listing.json()["datasets"]]


def test_the_file_of_an_upload_lives_inside_the_datasets_root(client, auth):
    """The upload is written under the uploads directory of the user."""
    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("inside.csv", CSV_CONTENT.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text

    root = Path(os.environ["DATASETS_ROOT"]).resolve()
    stored = [
        path for path in (root / "uploads").rglob("*.csv") if path.is_file()
    ]
    assert stored, "the upload was not written into the uploads directory"
    for path in stored:
        assert root in path.resolve().parents


def test_a_non_csv_file_is_refused(client, auth):
    """Only CSV files can be uploaded."""
    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )

    assert response.status_code == 400
    assert "csv" in response.json()["detail"].lower()


def test_an_empty_upload_is_refused(client, auth):
    """An empty file is not a dataset."""
    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 400


def test_a_file_without_rows_is_refused(client, auth):
    """A header without data is not a dataset."""
    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("header_only.csv", b"a,b,label\n", "text/csv")},
    )

    assert response.status_code == 400


def test_a_path_outside_of_the_root_is_refused():
    """The root is the boundary of what the application can read.

    Before the registry existed, the client sent a path and the server read
    it: an absolute path was used as it was, so any file of the server could
    be trained on.
    """
    with pytest.raises(DatasetError) as excinfo:
        resolve_storage_path("../../etc/passwd")
    assert "outside" in str(excinfo.value)

    with pytest.raises(DatasetError):
        resolve_storage_path("/etc/passwd")


def test_a_symlink_out_of_the_root_is_refused(tmp_path):
    """A symlink that points outside of the root does not open it."""
    outside = tmp_path / "outside.csv"
    outside.write_text(CSV_CONTENT)
    root = Path(os.environ["DATASETS_ROOT"])
    link = root / "data" / "link.csv"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(outside)
    try:
        with pytest.raises(DatasetError):
            resolve_storage_path("data/link.csv")
    finally:
        # The link is in the shared directory of the test run: it has to go
        # again, or the next start of the application would find it.
        link.unlink()


def test_the_dataset_of_another_user_is_not_found(client, auth):
    """A dataset that belongs to somebody else is not found.

    The answer must not tell the caller that the id exists.
    """
    uploaded = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("private.csv", CSV_CONTENT.encode(), "text/csv")},
    ).json()

    client.post(
        "/api/v1/register", json={"username": "other_user", "password": "secret123"}
    )
    other_token = client.post(
        "/token", data={"username": "other_user", "password": "secret123"}
    ).json()["access_token"]
    other = {"Authorization": f"Bearer {other_token}"}

    listing = client.get("/api/v1/ml/datasets", headers=other)
    assert uploaded["id"] not in [item["id"] for item in listing.json()["datasets"]]

    detail = client.get(f"/api/v1/ml/datasets/{uploaded['id']}", headers=other)
    assert detail.status_code == 404

    training = client.post(
        "/api/v1/ml/train",
        headers=other,
        json={
            "model_name": "Logistic_Regression",
            "dataset_id": uploaded["id"],
            "label_column": "label",
        },
    )
    assert training.status_code == 404


def test_the_built_in_datasets_are_registered(client, auth):
    """The datasets of the repository are registered at the startup."""
    listing = client.get("/api/v1/ml/datasets", headers=auth)
    assert listing.status_code == 200
    datasets = listing.json()["datasets"]

    names = {dataset["name"] for dataset in datasets}
    assert "sample_customer_churn.csv" in names
    assert "sample_house_prices.csv" in names

    for dataset in datasets:
        if dataset["source"] != "builtin":
            continue
        assert dataset["row_count"] > 0
        assert dataset["columns"]
        assert dataset["label_column"] in [column["name"] for column in dataset["columns"]]


def test_the_built_in_datasets_can_be_trained_on(client, auth):
    """A fresh clone can train a model without any setup."""
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
    metrics = response.json()["metrics"]
    assert metrics["accuracy"] > 0.5
    assert metrics["task_type"] == "classification"


def test_the_label_column_is_suggested():
    """A column with a usual name wins over the last column."""
    assert suggest_label([{"name": "a"}, {"name": "label"}]) == "label"
    assert suggest_label([{"name": "a"}, {"name": "b"}]) == "b"
    assert suggest_label([]) is None


def test_a_file_of_the_root_is_described(tmp_path):
    """The description of a file carries its columns and its rows."""
    path = Path(os.environ["DATASETS_ROOT"]) / "data" / "described.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CSV_CONTENT)

    columns, rows, label = describe_csv(path)

    assert [column["name"] for column in columns] == ["feature_a", "feature_b", "label"]
    assert rows == 4
    assert label == "label"


def test_an_upload_is_stored_with_a_generated_name():
    """The name of the client is never used to build a path."""
    name, storage_path = store_upload(42, "../../evil.csv", CSV_CONTENT.encode())

    assert name == "evil.csv"
    assert storage_path.startswith("uploads/42/")
    assert ".." not in storage_path
    assert resolve_storage_path(storage_path).exists()
