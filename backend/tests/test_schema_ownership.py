"""Tests for the schema ownership of the application.

The schema is owned by the Alembic migrations, not by the application: the app
never creates a table, it only verifies at startup that the tables the ORM
knows about exist. These tests pin that contract:

* the migrated schema matches the ORM (the migration chain cannot drift away
  from ``backend/app/models.py`` without the suite failing);
* the application refuses to start against a database that was not migrated,
  and says what to run;
* the deprecated ``on_event`` startup hook is gone.
"""

import asyncio
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.database import Base
from backend.app.main import app
import backend.app.main as main_module


DATABASE_PATH = make_url(os.environ["DATABASE_URL"]).database


def _tables_in(database_path):
    """The tables of a SQLite database."""
    connection = sqlite3.connect(database_path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()


def test_the_migrated_schema_matches_the_orm():
    """The tables the ORM declares are exactly the tables the migrations create.

    The test database is built by ``alembic upgrade head`` (see the session
    fixture in ``conftest.py``), so a drift between the migration chain and
    ``backend/app/models.py`` fails here instead of being papered over by the
    application.
    """
    migrated = _tables_in(DATABASE_PATH)
    declared = {table.name for table in Base.metadata.sorted_tables}

    assert declared <= migrated, (
        f"the migrations did not create the table(s) {sorted(declared - migrated)}"
    )
    # The vestigial "notes" table of the previous project must be gone.
    assert "notes" not in migrated


def test_the_startup_check_fails_with_an_actionable_message(tmp_path, monkeypatch):
    """An unmigrated database is a deployment error, not a runtime condition.

    The application must say what to run instead of failing with an opaque
    "no such table" further down.
    """
    empty_db = tmp_path / "empty.db"
    sqlite3.connect(empty_db).close()

    engine = create_async_engine(f"sqlite+aiosqlite:///{empty_db}")
    monkeypatch.setattr(main_module, "engine", engine)

    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(main_module.verify_schema())

    message = str(excinfo.value)
    assert "alembic upgrade head" in message
    assert "training_runs" in message

    asyncio.run(engine.dispose())


def test_the_application_uses_a_lifespan_handler_instead_of_on_event():
    """The deprecated startup hook must not come back.

    ``@app.on_event("startup")`` warns on every import and on every test run.
    A lifespan handler leaves the router's ``on_startup`` list empty.
    """
    assert app.router.on_startup == [], (
        "a startup event handler is registered: the deprecated on_event hook "
        "must not be used, the lifespan handler is the replacement"
    )
    assert app.router.lifespan_context is not None, (
        "the application has no lifespan handler"
    )


def test_the_app_starts_against_the_migrated_database():
    """The lifespan runs the schema check and lets a migrated database through."""
    with TestClient(app) as client:
        response = client.get("/api/v1/ml/models")
        assert response.status_code == 200
