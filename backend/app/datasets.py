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

import io
import os
import re
import shutil
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

# The number of bytes a stored file name may have. A file name is at most 255
# bytes on the usual file systems, and the stored name is the generated one
# followed by the name of the client.
MAX_FILE_NAME_BYTES = int(os.getenv("MAX_FILE_NAME_BYTES", "200"))

# The number of rows that are read at once when a file is inspected. The
# file is read in pieces, so that the memory of the process does not grow
# with the size of the file.
CSV_CHUNK_ROWS = 10000

# The number of columns a file may have. A file with a million columns takes
# gigabytes of memory to describe - one entry per column - and a table with a
# million columns is not a table this application can train on. The file is
# refused when its header has more columns than this.
MAX_UPLOAD_COLUMNS = int(os.getenv("MAX_UPLOAD_COLUMNS", "1000"))

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
    # The name is cut on the bytes and not on the characters: a file name is
    # at most 255 bytes, and a name of multi-byte characters would exceed it
    # long before it reaches 255 characters.
    encoded = cleaned.encode("utf-8")[:MAX_FILE_NAME_BYTES]
    cleaned = encoded.decode("utf-8", errors="ignore").rstrip("._ ")
    return cleaned or "dataset"


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


# The number of bytes of the header that are read to count the columns. A
# header that is longer than this has more columns than the limit anyway.
HEADER_SCAN_BYTES = 1024 * 1024

# The separators a file may use. The registry reads a comma separated file,
# but the count of the columns of a file is the same for every separator, and
# the file is refused before it is parsed.
CSV_SEPARATORS = (b",", b";", b"\t", b"|")


def _end_of_the_header(head: bytes, start: int) -> int:
    """The end of the header of a file, or -1 when it is not in the window.

    A quoted value may hold a line break, so the end of the header is the
    first line break that is not inside a quoted value. The parser of the
    training reads the header the same way.
    """
    in_quotes = False
    index = start
    while index < len(head):
        char = head[index : index + 1]
        if char == b'"':
            # Two quotes in a row inside a quoted value are an escaped quote.
            if in_quotes and head[index + 1 : index + 2] == b'"':
                index += 2
                continue
            in_quotes = not in_quotes
        elif char in (b"\n", b"\r") and not in_quotes:
            return index
        index += 1
    return -1


def _count_header_columns(stream) -> int:
    """The number of columns of a file, counted without parsing it.

    The header is read as bytes and the separators in it are counted.
    Parsing the file with pandas would cost a lot of memory and a lot of
    time when it has a lot of columns, and such a file is refused anyway.

    The count has to agree with the parser of the training, or the limit
    would not hold: the empty lines before the header are skipped, and a
    quoted value may hold a line break.

    The count is an upper bound: a separator inside a quoted name is counted
    as well. A file whose header holds a thousand separators inside one
    quoted name is refused, which is the safe direction.
    """
    head = stream.read(HEADER_SCAN_BYTES)
    if len(head) == HEADER_SCAN_BYTES and b"\n" not in head:
        # The header is longer than what was read: it holds more separators
        # than the limit allows.
        return MAX_UPLOAD_COLUMNS + 1

    # The empty lines before the header are skipped, the way the parser
    # skips them.
    start = 0
    while True:
        end_of_line = head.find(b"\n", start)
        if end_of_line == -1:
            if not head[start:].strip():
                # There is no header at all.
                return 1
            break
        if head[start:end_of_line].strip():
            break
        start = end_of_line + 1

    end = _end_of_the_header(head, start)
    if end == -1:
        # The header does not end inside the window: it holds more
        # separators than the limit allows.
        return MAX_UPLOAD_COLUMNS + 1

    header = head[start:end]
    return max(header.count(separator) for separator in CSV_SEPARATORS) + 1


def _scan_csv(stream, max_rows: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]:
    """The columns and the number of rows of a CSV file, read in pieces.

    The columns are counted before the file is parsed, and the file is
    refused when it has more of them than the application accepts: a file
    with a million columns takes gigabytes of memory to describe, and it is
    refused before that happens. The rows are then counted in pieces, so that
    the memory of the process does not grow with the size of the file. The
    types of the columns are the ones of the first rows.
    """
    stream.seek(0)
    columns_count = _count_header_columns(stream)
    if columns_count > MAX_UPLOAD_COLUMNS:
        raise DatasetError(
            f"The file has more than {MAX_UPLOAD_COLUMNS} columns."
        )
    stream.seek(0)

    columns: List[Dict[str, Any]] = []
    rows = 0
    for chunk in pd.read_csv(stream, chunksize=CSV_CHUNK_ROWS):
        if not columns:
            columns = [
                {"name": str(name), "dtype": str(dtype)}
                for name, dtype in zip(chunk.columns, chunk.dtypes)
            ]
        rows += len(chunk)
        if max_rows is not None and rows > max_rows:
            # The file is refused: there is no need to read the rest of it.
            raise DatasetError(
                f"The file has more than {max_rows} rows."
            )
    return columns, rows


def describe_csv(path: Path) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    """The columns, the number of rows and the suggested label of a CSV file.

    The file is read with the parser the training uses and in pieces, so that
    a file of fifty megabytes does not take fifty megabytes of memory. The
    rows are counted the way the reader counts them: a value may contain a
    line break inside quotes.
    """
    try:
        with path.open("rb") as handle:
            columns, rows = _scan_csv(handle)
    except pd.errors.EmptyDataError as exc:
        raise DatasetError(f"The dataset '{path.name}' is empty.") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise DatasetError(
            f"The dataset '{path.name}' could not be parsed as a CSV file: {exc}"
        ) from exc

    if not columns:
        raise DatasetError(f"The dataset '{path.name}' has no columns.")
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


def _as_stream(source):
    """The source of a file as a stream that can be read from the start."""
    if isinstance(source, (bytes, bytearray)):
        return io.BytesIO(source)
    source.seek(0)
    return source


def size_of(source) -> int:
    """The number of bytes of a file, without reading it."""
    if isinstance(source, (bytes, bytearray)):
        return len(source)
    position = source.tell()
    source.seek(0, os.SEEK_END)
    size = source.tell()
    source.seek(position)
    return size


def validate_upload(
    filename: str, source
) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
    """The description of an uploaded file, if the application can use it.

    The source is the bytes of the file or a stream that holds them. The
    content is parsed here, before the file is written: a file that the
    training could not read must not end up on the disk of the server. The
    description of the file is the answer, so that the file is not read a
    second time.
    """
    size = size_of(source)
    if size == 0:
        raise DatasetError("The uploaded file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise DatasetError(
            f"The uploaded file is {size} bytes, which is more than the "
            f"limit of {MAX_UPLOAD_BYTES} bytes."
        )
    if not filename.lower().endswith(".csv"):
        raise DatasetError("Only CSV files can be uploaded.")

    try:
        columns, rows = _scan_csv(_as_stream(source), max_rows=MAX_UPLOAD_ROWS)
    except pd.errors.EmptyDataError as exc:
        raise DatasetError("The uploaded file is empty.") from exc
    except UnicodeDecodeError as exc:
        raise DatasetError("The uploaded file is not a UTF-8 text file.") from exc
    except pd.errors.ParserError as exc:
        raise DatasetError(
            f"The uploaded file could not be parsed as a CSV file: {exc}"
        ) from exc

    if len(columns) < 2:
        raise DatasetError(
            "The uploaded file must be a CSV file with a comma as the separator "
            "and a header of at least two columns."
        )
    if rows == 0:
        raise DatasetError("The uploaded file has a header but no rows.")

    return columns, rows, suggest_label(columns)


def write_upload(owner_id: int, filename: str, source) -> Tuple[str, str]:
    """Write an uploaded file that was accepted already.

    The source is the bytes of the file or a stream that holds them: a file
    that is already on the disk is copied, and it is not read into the memory
    of the process.

    The directory of the user is resolved before the file is written: a
    directory that is a symlink to somewhere else is not a place where the
    application may write.
    """
    display_name = sanitize_name(filename)
    directory = uploads_dir() / str(owner_id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DatasetError(
            f"The uploads directory of the user could not be created: {exc}"
        ) from exc
    # The directory has to be inside the datasets root: a symlink that points
    # somewhere else would take the file out of the root.
    relative_storage_path(directory)
    stored_name = f"{uuid.uuid4().hex}_{display_name}"
    path = directory / stored_name
    try:
        if isinstance(source, (bytes, bytearray)):
            path.write_bytes(source)
        else:
            source.seek(0)
            with path.open("wb") as handle:
                shutil.copyfileobj(source, handle)
    except OSError:
        # A file that could not be written completely is not a dataset.
        path.unlink(missing_ok=True)
        raise DatasetError(
            f"The uploaded file could not be written: {path.name}."
        ) from None

    try:
        return display_name, relative_storage_path(path)
    except DatasetError:
        # The file was written outside of the root: it is removed again.
        path.unlink(missing_ok=True)
        raise


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
    """The directories of the repository that the vision models can use.

    A directory is a dataset of the vision models when it holds one
    subdirectory per class: a directory that holds something else is not
    registered, because a training on it would fail with an error of the
    image loader.
    """
    directory = builtin_datasets_dir()
    if not directory.exists():
        return []
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        # The directory cannot be read: there is no dataset in it.
        return []
    return [
        path
        for path in entries
        if path.is_dir()
        and not path.name.startswith(".")
        and _holds_class_directories(path)
    ]


def _holds_class_directories(path: Path) -> bool:
    """Whether a directory holds the subdirectories of an image dataset."""
    try:
        return any(child.is_dir() for child in path.iterdir())
    except OSError:
        return False


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
