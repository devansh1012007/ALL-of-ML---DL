"""The dataset registry.

A dataset is a row of the ``datasets`` table, not a path that the client
sends. The registry is the only place that turns a row into a path, and every
path it produces is inside the datasets root. That is what makes the "read
any file of the server" primitive impossible: the client refers to a dataset
by its id, and the server decides what that id means.

Three kinds of datasets exist:

* the **built-in** ones, the CSV files of ``data/`` in the repository. They
  are seeded as rows at startup, so a fresh clone has something to train on.
* the **uploads**, the files a user sends. They belong to that user.
* the **folders**, the directories with one subdirectory per class that the
  vision models need.
"""

import csv
import io
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .settings import builtin_datasets_dir, datasets_root, uploads_dir


# The limits of an upload. They exist so that a single request cannot fill
# the disk of the server or the memory of the process.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
MAX_UPLOAD_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "2000000"))

# The number of columns that are reported for a dataset. The listing returns
# the columns of every dataset, and a file with thousands of columns would
# make it enormous.
MAX_REPORTED_COLUMNS = int(os.getenv("MAX_REPORTED_COLUMNS", "200"))

# The names a label column usually has. The registry suggests the first one
# that is in the file.
LABEL_COLUMN_NAMES = ("label", "target", "y", "class", "outcome", "churn")

# The characters a file name may not contain. The name of an upload is never
# used to build a path (the upload gets a generated name), but it is shown to
# the user and it ends up in the name of the stored file, so a path separator
# and the control characters are removed. The letters of every script are
# kept: a name that loses its non-ASCII characters is not a name the user
# recognises any more.
_UNSAFE_NAME = re.compile(r"[\x00-\x1f\x7f/\\]")


class DatasetError(ValueError):
    """A dataset could not be read, stored or described."""


def sanitize_name(name: str) -> str:
    """A file name that is safe to show and to store."""
    cleaned = _UNSAFE_NAME.sub("_", (name or "").strip())
    cleaned = cleaned.strip("._ ") or "dataset"
    return cleaned[:120]


def resolve_storage_path(storage_path: str) -> Path:
    """The absolute path of a dataset, guaranteed to be inside the root.

    The path of a dataset is relative to the datasets root. An absolute path,
    a path that climbs out of the root with ``..`` or a path that points at a
    symlink outside of the root are all refused: the registry is the boundary
    of what the application can read.
    """
    if "\x00" in storage_path:
        raise DatasetError("The dataset path contains an invalid character.")
    root = datasets_root()
    candidate = (root / storage_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise DatasetError(
            f"The dataset path '{storage_path}' points outside of the datasets "
            f"directory."
        )
    return candidate


def relative_storage_path(path: Path) -> str:
    """The path of a file, relative to the datasets root.

    A file whose real path is outside of the root - a symlink that points
    somewhere else - has no relative path: it is not a dataset of this
    application.
    """
    root = datasets_root()
    try:
        return str(path.resolve().relative_to(root))
    except ValueError as exc:
        raise DatasetError(
            f"The file '{path.name}' points outside of the datasets directory."
        ) from exc


def describe_csv(path: Path) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    """The columns, the number of rows and the suggested label of a CSV file.

    The header is read with pandas, so the types are the ones the first rows
    of the file have. The rows are counted with the CSV parser, so that a file
    with a quoted line break is counted the way a reader would count it.
    """
    try:
        frame = pd.read_csv(path, nrows=100)
    except pd.errors.EmptyDataError as exc:
        raise DatasetError(f"The dataset '{path.name}' is empty.") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise DatasetError(
            f"The dataset '{path.name}' could not be parsed as a CSV file: {exc}"
        ) from exc

    columns = [
        {"name": str(name), "dtype": str(dtype)}
        for name, dtype in zip(frame.columns, frame.dtypes)
    ]
    if not columns:
        raise DatasetError(f"The dataset '{path.name}' has no columns.")

    rows = _count_rows(path)
    if rows == 0:
        raise DatasetError(f"The dataset '{path.name}' has a header but no rows.")

    return columns, rows, suggest_label(columns)


def suggest_label(columns: List[Dict[str, Any]]) -> Optional[str]:
    """The column that is most likely to be the label.

    A column with one of the usual names wins. Otherwise the last column is
    the suggestion: in a table that was exported for a training, the target
    is usually the last one.
    """
    names = [column["name"] for column in columns]
    for candidate in LABEL_COLUMN_NAMES:
        for name in names:
            if name.strip().lower() == candidate:
                return name
    return names[-1] if names else None


def _count_rows(path: Path) -> int:
    """The number of data rows of a CSV file.

    The rows are counted with the CSV parser and not by counting the line
    breaks: a value may contain a line break inside quotes, and a file whose
    last line has no line break would be counted one row too few.
    """
    rows = 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)  # the header
        except StopIteration:
            return 0
        for _ in reader:
            rows += 1
    return rows


def validate_upload(filename: str, content: bytes) -> None:
    """Whether an uploaded file is a CSV file the application can use.

    The content is parsed here, before the file is written: a file that the
    training could not read must not end up on the disk of the server.
    """
    if not content:
        raise DatasetError("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise DatasetError(
            f"The uploaded file is {len(content)} bytes, which is more than the "
            f"limit of {MAX_UPLOAD_BYTES} bytes."
        )
    if not filename.lower().endswith(".csv"):
        raise DatasetError("Only CSV files can be uploaded.")

    # The first line must be a header with at least two columns, and there has
    # to be at least one data row.
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetError("The uploaded file is not a UTF-8 text file.") from exc

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise DatasetError("The uploaded file is empty.") from exc
    if len(header) < 2:
        raise DatasetError(
            "The uploaded file must have a header with at least two columns."
        )

    rows = 0
    for _ in reader:
        rows += 1
        if rows > MAX_UPLOAD_ROWS:
            raise DatasetError(
                f"The uploaded file has more than {MAX_UPLOAD_ROWS} rows."
            )
    if rows == 0:
        raise DatasetError("The uploaded file has a header but no rows.")

    # The file has to be readable by the training: a file that pandas refuses
    # is refused here, while it is still in the memory of the request.
    try:
        pd.read_csv(io.StringIO(text, newline=""))
    except pd.errors.EmptyDataError as exc:
        raise DatasetError("The uploaded file is empty.") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise DatasetError(
            f"The uploaded file could not be parsed as a CSV file: {exc}"
        ) from exc


def store_upload(owner_id: int, filename: str, content: bytes) -> Tuple[str, str]:
    """Write an uploaded file and return its name and its storage path.

    The file is written under the uploads directory of the user, with a
    generated name: the name of the client is only used for the display, never
    for the path. It is written only after the content was accepted, so that a
    rejected upload does not leave a file behind.
    """
    validate_upload(filename, content)

    display_name = sanitize_name(filename)
    directory = uploads_dir() / str(owner_id)
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{display_name}"
    path = directory / stored_name
    path.write_bytes(content)

    return display_name, relative_storage_path(path)


def unique_dataset_name(name: str, taken: Iterable[str]) -> str:
    """A dataset name that is not used yet.

    Two users may upload a file with the same name, and a built-in dataset
    may have the name of an upload. The name is only a convenience - a
    training refers to a dataset by its id - but it has to be unambiguous for
    the display.
    """
    used = {item.lower() for item in taken}
    if name.lower() not in used:
        return name
    for suffix in range(2, 1000):
        candidate = f"{name} ({suffix})"
        if candidate.lower() not in used:
            return candidate
    return f"{name} ({uuid.uuid4().hex[:8]})"


def builtin_files() -> List[Path]:
    """The CSV files that ship with the repository."""
    directory = builtin_datasets_dir()
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.glob("*.csv")
        if path.is_file() and not path.name.startswith(".")
    )


def builtin_folders() -> List[Path]:
    """The directories of the repository that the vision models can use."""
    directory = builtin_datasets_dir()
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )


def dataset_to_dict(dataset) -> Dict[str, Any]:
    """The representation of a dataset in the API.

    The columns are capped: a file with thousands of columns would otherwise
    make the listing of the datasets enormous, and the form only needs the
    names of a few of them.
    """
    columns = dataset.columns or []
    return {
        "id": dataset.id,
        "name": dataset.name,
        "source": dataset.source,
        "size_bytes": dataset.size_bytes,
        "row_count": dataset.row_count,
        "columns": columns[:MAX_REPORTED_COLUMNS],
        "column_count": len(columns),
        "label_column": dataset.label_column,
        "owner_id": dataset.owner_id,
    }
