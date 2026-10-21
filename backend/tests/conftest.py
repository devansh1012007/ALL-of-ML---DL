"""Test bootstrap for the backend test suite.

Three things have to happen before any ``backend.app`` module is imported:

1. ``DATABASE_URL`` must point at an isolated database. ``backend/app/database.py``
   reads the variable and builds the async engine at import time, so setting it
   here (conftest is imported before the test modules) keeps the suite away
   from a real database and stops ``./backend.db`` from being created in the
   repository root.
2. The repository root has to be importable. ``backend/`` and ``backend/app/``
   are namespace packages (no ``__init__.py``), so ``backend.app.*`` only
   resolves when the repository root is on ``sys.path``. Adding it here makes
   both ``pytest backend/tests`` and ``python -m pytest backend/tests`` work
   from the repository root.
3. The model artifacts must not be written into the repository. ``MODEL_DIR``
   is an absolute path into the repository, so it is redirected to a temporary
   directory for every test (see ``isolated_model_dir``).

The synthetic datasets are generated here as well so that every test module
works on exactly the same, deterministic data.
"""

import atexit
import os
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_TMP_DB_DIR = tempfile.mkdtemp(prefix="all-of-ml-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_TMP_DB_DIR, 'test.db')}"


def _remove_tmp_db_dir():
    shutil.rmtree(_TMP_DB_DIR, ignore_errors=True)


# The directory has to exist before the first ``backend.app`` import (the database
# URL is read at import time), but it is removed by an ``atexit`` hook: the process
# that creates the directory is always the process that cleans it up. A pytest-xdist
# controller imports the conftest but never runs the session fixtures, so a
# session-scoped teardown alone leaks one directory per parallel run.
atexit.register(_remove_tmp_db_dir)


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_database():
    """Remove the temporary database directory once the session is over."""
    yield
    _remove_tmp_db_dir()


@pytest.fixture(scope="session", autouse=True)
def _migrated_test_database():
    """Create the schema with Alembic -- the same path production uses.

    The application deliberately does not call ``Base.metadata.create_all`` any
    more: the schema is owned by the migrations, and the app only verifies it
    at startup. Building the test schema with the migrations therefore also
    means the suite fails when the migration chain drifts away from
    ``backend/app/models.py``.

    The migration runs against the throwaway database of the
    ``DATABASE_URL`` that is set above, so the repository is never touched.
    """
    from alembic import command
    from alembic.config import Config

    backend_dir = os.path.join(REPO_ROOT, "backend")
    config = Config(os.path.join(backend_dir, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def isolated_model_dir(tmp_path, monkeypatch):
    """Redirect the model artifacts into a per-test temporary directory.

    ``write_artifact()`` reads the ``MODEL_DIR`` module global when it is called,
    so patching the attribute is enough to keep the suite from writing artifacts
    into the repository's ``models/`` directory. The directory is returned so a
    test can assert that an artifact really landed there.
    """
    from backend.app import model_training

    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(model_training, "MODEL_DIR", models_dir)
    return models_dir


# --- synthetic datasets ------------------------------------------------------
#
# The catalog entries need a dataset that is big enough for their own parameters:
# K-Mean asks for 8 clusters, KNN for 5 neighbours, PCA for 2 components and t-SNE
# for a perplexity of 30. Six rows (the size of the original fixture) is not enough
# for any of them, so the datasets below have 60 rows.

FEATURE_COLUMNS = ("feature_0", "feature_1", "feature_2", "feature_3")
DATASET_ROWS = 60
CLASSIFICATION_SEED = 20240520
REGRESSION_SEED = 20240521


def _classification_frame(n_rows: int = DATASET_ROWS) -> pd.DataFrame:
    """Two tight, well separated clusters: learnable and dense enough for DBSCAN."""
    rng = np.random.RandomState(CLASSIFICATION_SEED)
    labels = np.array([index % 2 for index in range(n_rows)])
    centers = np.array([[-1.5] * len(FEATURE_COLUMNS), [1.5] * len(FEATURE_COLUMNS)])
    features = centers[labels] + rng.normal(scale=0.05, size=(n_rows, len(FEATURE_COLUMNS)))
    frame = pd.DataFrame(features, columns=list(FEATURE_COLUMNS))
    frame["label"] = labels
    return frame


def _regression_frame(n_rows: int = DATASET_ROWS) -> pd.DataFrame:
    """A continuous target that is a linear function of the first two features."""
    rng = np.random.RandomState(REGRESSION_SEED)
    features = rng.normal(loc=0.0, scale=1.0, size=(n_rows, len(FEATURE_COLUMNS)))
    frame = pd.DataFrame(features, columns=list(FEATURE_COLUMNS))
    frame["label"] = (
        3.0 * features[:, 0]
        + 2.0 * features[:, 1]
        - 1.0
        + rng.normal(scale=0.05, size=n_rows)
    )
    return frame


@pytest.fixture(scope="session")
def classification_dataset(tmp_path_factory):
    """Path of the deterministic two-class dataset."""
    path = tmp_path_factory.mktemp("datasets") / "classification.csv"
    _classification_frame().to_csv(path, index=False)
    return path


@pytest.fixture(scope="session")
def regression_dataset(tmp_path_factory):
    """Path of the deterministic regression dataset (continuous label)."""
    path = tmp_path_factory.mktemp("datasets") / "regression.csv"
    _regression_frame().to_csv(path, index=False)
    return path
