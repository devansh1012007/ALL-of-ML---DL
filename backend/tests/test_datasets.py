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

import io
import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.datasets import (
    DatasetError,
    describe_csv,
    resolve_storage_path,
    suggest_label,
    validate_upload,
    write_upload,
)
from backend.app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_CONTENT = "feature_a,feature_b,label\n1,2,0\n3,4,1\n5,6,0\n7,8,1\n"


def store_upload(owner_id: int, filename: str, content: bytes):
    """What the endpoint does: the content is accepted, and then written."""
    validate_upload(filename, content)
    return write_upload(owner_id, filename, content)


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


def test_the_file_of_an_upload_that_could_not_be_registered_is_removed(
    client, auth, monkeypatch
):
    """A file that no row points at is removed again.

    The row is written after the file, and a database that refuses the row
    leaves a file that nobody can reach.
    """
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncSession

    root = Path(os.environ["DATASETS_ROOT"]).resolve()
    uploads = root / "uploads"
    before = set(uploads.rglob("*.csv")) if uploads.exists() else set()

    async def refuse(self, *args, **kwargs):
        raise IntegrityError("statement", {}, Exception("refused"))

    monkeypatch.setattr(AsyncSession, "commit", refuse)

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("refused.csv", CSV_CONTENT.encode(), "text/csv")},
    )

    assert response.status_code == 400
    after = set(uploads.rglob("*.csv")) if uploads.exists() else set()
    assert after == before, f"the file of the refused upload stayed on the disk: {after - before}"


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


def test_the_built_in_datasets_can_be_trained_on(client, auth, wait_for_run):
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
    run = wait_for_run(client, auth, response.json()["run_id"])
    assert run["status"] == "completed", run
    metrics = run["metrics"]
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


def test_two_uploads_of_the_same_file_get_different_paths():
    """The stored name is generated, so two uploads never share a file.

    The name of the client is only the display name: if it were part of the
    path, the second upload of the same file would overwrite the first one.
    """
    first_name, first_path = store_upload(42, "same.csv", CSV_CONTENT.encode())
    second_name, second_path = store_upload(42, "same.csv", CSV_CONTENT.encode())

    assert first_name == second_name == "same.csv"
    assert first_path != second_path
    # The generated part comes first, so the file name of the client is only
    # the tail of the stored name.
    assert first_path.rsplit("/", 1)[-1].startswith(
        first_path.rsplit("/", 1)[-1].split("_", 1)[0]
    )
    assert len(first_path.rsplit("/", 1)[-1].split("_", 1)[0]) == 32
    assert resolve_storage_path(first_path).exists()
    assert resolve_storage_path(second_path).exists()


def test_the_dataset_of_the_owner_is_returned_by_its_id(client, auth):
    """The detail of a dataset carries its columns and its label."""
    uploaded = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("detail.csv", CSV_CONTENT.encode(), "text/csv")},
    ).json()

    response = client.get(f"/api/v1/ml/datasets/{uploaded['id']}", headers=auth)

    assert response.status_code == 200, response.text
    dataset = response.json()
    assert dataset["id"] == uploaded["id"]
    assert [column["name"] for column in dataset["columns"]] == [
        "feature_a",
        "feature_b",
        "label",
    ]
    assert dataset["label_column"] == "label"
    assert dataset["row_count"] == 4


def test_an_upload_with_too_many_rows_is_refused(client, auth, monkeypatch):
    """The number of rows of an upload is limited."""
    from backend.app import datasets as datasets_module

    monkeypatch.setattr(datasets_module, "MAX_UPLOAD_ROWS", 2)

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("too_many_rows.csv", CSV_CONTENT.encode(), "text/csv")},
    )

    assert response.status_code == 400
    assert "rows" in response.json()["detail"].lower()


def test_an_upload_that_is_too_big_is_refused(client, auth, monkeypatch):
    """The size of an upload is limited."""
    from backend.app import datasets as datasets_module

    monkeypatch.setattr(datasets_module, "MAX_UPLOAD_BYTES", 10)

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("too_big.csv", CSV_CONTENT.encode(), "text/csv")},
    )

    assert response.status_code == 400
    assert "limit" in response.json()["detail"].lower()


def test_a_refused_upload_leaves_no_file_behind(client, auth):
    """A file that was refused is not written to the disk.

    The content is checked before it is written, so a rejected upload does not
    fill the disk of the server with files nobody can use.
    """
    root = Path(os.environ["DATASETS_ROOT"]).resolve()
    uploads = root / "uploads"
    before = sorted(path.name for path in uploads.rglob("*")) if uploads.exists() else []

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("broken.csv", b'a,b,label\n"unclosed,2,0\n', "text/csv")},
    )
    assert response.status_code == 400

    after = sorted(path.name for path in uploads.rglob("*")) if uploads.exists() else []
    assert after == before


def test_the_name_of_an_upload_is_unique(client, auth):
    """Two uploads with the same name get two different names.

    The name is what the user sees, so it has to say which file it is.
    """
    first = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("same.csv", CSV_CONTENT.encode(), "text/csv")},
    ).json()
    second = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("same.csv", CSV_CONTENT.encode(), "text/csv")},
    ).json()

    assert first["id"] != second["id"]
    assert first["name"] != second["name"]


def test_the_upload_is_rate_limited(client, auth, monkeypatch):
    """A client cannot fill the disk of the server with uploads."""
    from backend.app import main as main_module

    monkeypatch.setattr(main_module, "UPLOAD_RATE_LIMIT", 2)

    for _ in range(2):
        response = client.post(
            "/api/v1/ml/datasets/upload",
            headers=auth,
            files={"file": ("rate.csv", CSV_CONTENT.encode(), "text/csv")},
        )
        assert response.status_code == 200, response.text

    refused = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("rate.csv", CSV_CONTENT.encode(), "text/csv")},
    )
    assert refused.status_code == 429


def test_the_row_count_of_a_file_with_a_quoted_line_break(tmp_path):
    """The rows are counted the way a CSV reader counts them.

    A value may contain a line break inside quotes: counting the line breaks
    would report one row too many.
    """
    path = Path(os.environ["DATASETS_ROOT"]) / "data" / "quoted.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('a,b,label\n"first\nsecond",2,0\n3,4,1\n')

    columns, rows, label = describe_csv(path)

    assert rows == 2
    assert label == "label"


def test_the_columns_carry_the_type_of_the_values(tmp_path):
    """The description of a file carries the types the training will see."""
    path = Path(os.environ["DATASETS_ROOT"]) / "data" / "typed.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("count,value,label\n1,1.5,0\n2,2.5,1\n")

    columns, _, _ = describe_csv(path)

    types = {column["name"]: column["dtype"] for column in columns}
    assert types["count"] == "int64"
    assert types["value"] == "float64"


def test_a_file_with_too_many_columns_is_refused(client, auth):
    """A file with a lot of columns is refused before it is parsed.

    A file with a lot of columns takes gigabytes of memory to describe - one
    entry per column - and it is refused when its header is counted, before
    the table of it is built.
    """
    from backend.app import datasets as registry

    content = ("c0,c1,c2,c3,c4,c5,c6,c7,c8,c9\n" + "1,2,3,4,5,6,7,8,9,0\n").encode()

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("wide.csv", content, "text/csv")},
    )

    assert response.status_code == 200, response.text

    # With a limit of five columns, the same file is refused.
    previous = registry.MAX_UPLOAD_COLUMNS
    registry.MAX_UPLOAD_COLUMNS = 5
    try:
        refused = client.post(
            "/api/v1/ml/datasets/upload",
            headers=auth,
            files={"file": ("wide.csv", content, "text/csv")},
        )
    finally:
        registry.MAX_UPLOAD_COLUMNS = previous

    assert refused.status_code == 400, refused.text
    assert "columns" in refused.json()["detail"].lower()


@pytest.mark.parametrize(
    "prefix",
    [
        b"",
        b"\n",
        b"\r\n",
        b"\n\n",
        b"   \n",
        b'"a\nb",c,d,label\n',  # a quoted value with a line break in it
    ],
    ids=["plain", "a leading newline", "a leading crlf", "two newlines", "a blank line", "a quoted newline"],
)
def test_the_count_of_the_columns_agrees_with_the_parser(prefix):
    """The count of the columns may not be fooled by the header.

    The parser of the training skips the empty lines before the header and
    reads a quoted value with a line break in it as one value: the count
    that decides whether the file is refused has to agree with it, or the
    limit does not hold.
    """
    from backend.app.datasets import _count_header_columns

    header = b"a,b,c,label\n1,2,3,0\n"
    content = prefix + header

    counted = _count_header_columns(io.BytesIO(content))
    parsed = len(pd.read_csv(io.BytesIO(content), nrows=0).columns)

    assert counted == parsed, f"counted {counted}, the parser sees {parsed}"


def test_a_file_with_a_leading_newline_and_many_columns_is_refused(client, auth):
    """The limit of the columns holds for a file that starts with a newline."""
    from backend.app import datasets as registry

    columns = ",".join(f"c{index}" for index in range(50))
    content = ("\n" + columns + "\n" + ",".join("1" for _ in range(50)) + "\n").encode()

    previous = registry.MAX_UPLOAD_COLUMNS
    registry.MAX_UPLOAD_COLUMNS = 10
    try:
        response = client.post(
            "/api/v1/ml/datasets/upload",
            headers=auth,
            files={"file": ("wide.csv", content, "text/csv")},
        )
    finally:
        registry.MAX_UPLOAD_COLUMNS = previous

    assert response.status_code == 400, response.text
    assert "columns" in response.json()["detail"].lower()


def test_a_request_with_two_datasets_is_refused(client, auth):
    """A request carries either a dataset of the registry or a Hugging Face one.

    The plan says exactly one: a request that carries both would silently
    train on the local one and ignore the other.
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
            "hf_dataset_url": "https://huggingface.co/datasets/some/one",
            "label_column": "label",
            "test_size": 0.2,
            "random_state": 42,
            "hyperparameters": {},
            "mode": "manual",
        },
    )

    assert response.status_code == 400, response.text
    assert "both" in response.json()["detail"].lower()


def test_the_name_of_an_upload_keeps_its_letters():
    """The name of a file is shown to the user, so it keeps its letters."""
    name, _ = store_upload(43, "üñíçø∂é.csv", CSV_CONTENT.encode())

    assert name == "üñíçø∂é.csv"


def test_a_name_of_multi_byte_characters_stays_a_valid_file_name():
    """A long name of multi-byte characters is a file name, not an error.

    A file name is at most 255 bytes, and the characters of every script
    take more than one byte: the name is cut on the bytes.
    """
    name, storage_path = store_upload(44, "é" * 300 + ".csv", CSV_CONTENT.encode())

    assert name
    assert len(name.encode("utf-8")) <= 200
    # The file was written: the name fits the file system.
    assert resolve_storage_path(storage_path).exists()


def test_a_file_the_training_could_not_read_is_refused_with_a_message(client, auth):
    """A file the parser refuses is a 400, not a crash of the server.

    The parser of the training is the one that decides: a file it cannot
    read is not a dataset, and the client has to see why.
    """
    content = b'a,b,label\n"unclosed,2,0\n'

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("broken.csv", content, "text/csv")},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]


def test_a_column_with_a_long_text_is_a_dataset(client, auth):
    """A long value is not an error.

    The parser of the standard library refuses a field of more than 128 KB,
    while the training reads the file with pandas, which has no such limit: a
    column with a long text is a dataset.
    """
    content = ("a,b,label\n" + "x" * 200_000 + ",2,0\n").encode()

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("wide.csv", content, "text/csv")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["row_count"] == 1


def test_a_malformed_file_in_the_data_directory_does_not_stop_the_startup():
    """One broken file in data/ must not keep the server from starting.

    The data directory belongs to the user: a file that the application
    cannot read is skipped with a warning, and the other datasets stay
    usable.
    """
    root = Path(os.environ["DATASETS_ROOT"])
    broken = root / "data" / "broken.csv"
    broken.parent.mkdir(parents=True, exist_ok=True)
    # A file that the parser of the training refuses.
    broken.write_bytes(b'a,b,label\n"unclosed,2,0\n')

    try:
        # The startup of the application registers the datasets of the
        # directory: it has to come up with the broken file there.
        with TestClient(app) as started:
            # The application answers: it did not stop at the broken file.
            assert started.get("/openapi.json").status_code == 200
    finally:
        broken.unlink()


def test_an_oversized_upload_is_refused_before_the_body_is_read(client, auth, monkeypatch):
    """The body of an upload that is too big is never read.

    The framework writes the file part of a request to a temporary file
    before the endpoint runs, so a limit that is only checked in the endpoint
    does not bound the disk of the server.
    """
    from backend.app import datasets as registry

    monkeypatch.setattr(registry, "MAX_UPLOAD_BYTES", 1024)
    content = ("a,b,label\n" + "\n".join(f"{i},2,0" for i in range(5000))).encode()

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers=auth,
        files={"file": ("big.csv", content, "text/csv")},
    )

    assert response.status_code == 413, response.text


def test_an_upload_without_a_length_is_refused_as_well(client, auth, monkeypatch):
    """A request that does not announce its length is refused too.

    A client can send the body in pieces, without a Content-Length header.
    The guard cannot ask the client how big the body is then, so it counts
    the bytes as they arrive and refuses the request as soon as it is bigger
    than the limit - before the framework writes it to the disk.
    """
    from backend.app import datasets as registry

    monkeypatch.setattr(registry, "MAX_UPLOAD_BYTES", 1024)

    def chunks():
        yield b"--boundary\r\n"
        yield b'Content-Disposition: form-data; name="file"; filename="big.csv"\r\n'
        yield b"Content-Type: text/csv\r\n\r\n"
        # The body is sent in pieces, so that no length is announced.
        for _ in range(20):
            yield b"a,b,label\n" + b"1,2,0\n" * 500
        yield b"\r\n--boundary--\r\n"

    response = client.post(
        "/api/v1/ml/datasets/upload",
        headers={**auth, "Content-Type": "multipart/form-data; boundary=boundary"},
        content=chunks(),
    )

    assert response.status_code == 413, response.text
