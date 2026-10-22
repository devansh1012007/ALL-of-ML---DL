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
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_TMP_DB_DIR = tempfile.mkdtemp(prefix="all-of-ml-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{os.path.join(_TMP_DB_DIR, 'test.db')}"

# The datasets of the test run live in a temporary directory: a dataset is a
# path relative to this root, and the suite must not read the datasets of the
# repository nor write an upload into it.
_TMP_DATASETS_DIR = tempfile.mkdtemp(prefix="all-of-ml-datasets-")
os.environ["DATASETS_ROOT"] = _TMP_DATASETS_DIR

# The signing key of the tokens. The application generates a random key in
# ``<repo>/.secret_key`` when none is set, which would write into the
# repository during the test run. The tests bring their own key instead.
os.environ["SECRET_KEY"] = "test-signing-key-for-the-backend-test-suite"


def _remove_tmp_db_dir():
    shutil.rmtree(_TMP_DB_DIR, ignore_errors=True)
    shutil.rmtree(_TMP_DATASETS_DIR, ignore_errors=True)


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


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Start every test with an empty rate-limit budget.

    The limiter counts the attempts of a client, and every test client shares
    the same address, so without this a test that fails a login would spend
    the budget of the tests that follow it.
    """
    from backend.app.main import reset_rate_limits

    reset_rate_limits()
    yield
    reset_rate_limits()


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


def datasets_root_dir():
    """The directory the datasets of the test run live in.

    The application reads its datasets from the root of the ``DATASETS_ROOT``
    environment variable, and a dataset is a path *relative* to it. The tests
    point that variable at a temporary directory, so the suite never reads
    the datasets of the repository and never writes an upload into it.

    The sample datasets of the repository are copied into that directory, so
    the startup registers them the way it does in a real installation.
    """
    root = Path(os.environ["DATASETS_ROOT"])
    (root / "data").mkdir(parents=True, exist_ok=True)
    for sample in sorted((Path(REPO_ROOT) / "data").glob("sample_*.csv")):
        target = root / "data" / sample.name
        if not target.exists():
            shutil.copyfile(sample, target)
    return root


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


@pytest.fixture(scope="session", autouse=True)
def _datasets_root():
    """Prepare the datasets directory before anything starts the application.

    The application registers the datasets of the root when it starts, so the
    directory has to exist before the first client is created.
    """
    datasets_root_dir()
    yield


@pytest.fixture(scope="session")
def classification_dataset(tmp_path_factory):
    """The storage path of the deterministic two-class dataset."""
    root = datasets_root_dir()
    path = root / "data" / "classification.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    _classification_frame().to_csv(path, index=False)
    return "data/classification.csv"


@pytest.fixture(scope="session")
def regression_dataset(tmp_path_factory):
    """The storage path of the deterministic regression dataset (continuous label)."""
    root = datasets_root_dir()
    path = root / "data" / "regression.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    _regression_frame().to_csv(path, index=False)
    return "data/regression.csv"
