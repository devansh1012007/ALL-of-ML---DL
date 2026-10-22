"""The configuration of the application.

The database URL is resolved here and nowhere else, so that the application
and the Alembic migrations cannot drift apart: both read the same value, and
importing this module has no side effect (it creates no engine, opens no
connection).
"""

import os
from pathlib import Path

# The root of the repository. The application and the migrations resolve their
# paths against it, so the two cannot disagree about where the data lives.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The URL of the database. It is read once, at import time, because the engine
# is built from it. ``DATABASE_URL`` always wins; the fallback is the local
# SQLite file, which makes a fresh checkout runnable without any setup.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./backend.db")


def datasets_root() -> Path:
    """The directory every dataset is read from.

    A dataset is a row of the registry, and the row carries a path *relative*
    to this root. The client never sends a path, so this root is the boundary:
    a dataset that is not inside it cannot be trained, whatever the row says.

    The value is read on every call, so a test (or a deployment) can point it
    somewhere else.
    """
    return Path(os.getenv("DATASETS_ROOT", str(REPO_ROOT))).resolve()


def builtin_datasets_dir() -> Path:
    """The directory of the datasets that ship with the repository."""
    return datasets_root() / "data"


def uploads_dir() -> Path:
    """The directory the uploaded datasets are written to."""
    return datasets_root() / "uploads"
