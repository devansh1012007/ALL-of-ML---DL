"""add training_runs table, drop the vestigial notes table

Revision ID: c4a9e2b17d3f
Revises: 7f9590585a2a
Create Date: 2026-10-22 09:00:00.000000

The ``notes`` table is a vestige of the previous "PrimeTrade Secure Notes API"
project. It is referenced by no ORM model, no route and no frontend view, and
``backend/app.log`` still contains its log lines from 2026-03-25. The
``training_runs`` table is the one the application actually needs and was, until
now, only ever created behind Alembic's back by ``Base.metadata.create_all``.

The DDL is idempotent on purpose. A real database is in one of three states:

* migrated to ``7f9590585a2a`` (users + notes),
* touched only by ``create_all`` (users + training_runs),
* or both.

A plain revision fails on two of the three with ``DuplicateTableError``, so
every step is guarded by the table list of the live database. A table that
exists but has the wrong columns is *repaired* rather than accepted: a
database created by an older version of the application has the right table
name but not the current columns, and the application would then fail on the
first query that touches a missing column.
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4a9e2b17d3f"
down_revision: Union[str, Sequence[str], None] = "7f9590585a2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The schema of a fresh database before this revision, used in offline mode
# (``alembic upgrade head --sql``), where the live database cannot be
# inspected. The offline SQL is the DDL of a fresh installation.
_TABLES_BEFORE = frozenset({"users", "notes"})
_INDEXES_BEFORE = {
    "users": frozenset({"ix_users_id", "ix_users_username"}),
    "notes": frozenset({"ix_notes_id"}),
    "training_runs": frozenset(),
}

# The columns of ``training_runs`` and how to add the missing ones. The list
# mirrors ``backend/app/models.py``; the drift test in the test suite fails if
# the two disagree.
_TRAINING_RUNS_COLUMNS = (
    ("id", sa.Integer(), False, None),
    ("owner_id", sa.Integer(), False, None),
    ("model_name", sa.String(), False, None),
    ("dataset_source", sa.String(), False, None),
    ("dataset_tag", sa.String(), False, None),
    ("hf_dataset_url", sa.String(), True, None),
    ("mode", sa.String(), False, None),
    ("env_id", sa.String(), True, None),
    ("optimize_metric", sa.String(), True, None),
    ("model_candidates", sa.JSON(), True, None),
    ("hyperparameters", sa.JSON(), False, None),
    ("metrics", sa.JSON(), True, None),
    ("artifact_path", sa.String(), True, None),
    ("status", sa.String(), False, None),
    ("created_at", sa.DateTime(timezone=True), True, sa.func.now()),
    ("updated_at", sa.DateTime(timezone=True), True, sa.func.now()),
)


def _existing_tables() -> set:
    """The tables that exist in the database the migration runs against."""
    if context.is_offline_mode():
        return set(_TABLES_BEFORE)
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set:
    """The names of the indexes of ``table``."""
    if context.is_offline_mode():
        return set(_INDEXES_BEFORE.get(table, frozenset()))
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table)}


def _existing_columns(table: str) -> set:
    """The names of the columns of ``table``."""
    if context.is_offline_mode():
        return set()
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _row_count(table: str) -> int:
    """The number of rows of ``table``."""
    return (
        op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0
    )


def _create_index_if_missing(name: str, table: str, columns) -> None:
    """Create an index unless the table already carries it.

    A database that was created by ``create_all`` before the owner index was
    added to the ORM has the table but not the index, so the index is checked
    independently of the table.
    """
    if name not in _existing_indexes(table):
        op.create_index(name, table, columns, unique=False)


def _drop_table_if_empty(table: str) -> None:
    """Drop ``table`` - but never a table that still holds data.

    This chain may run on a database that the application created itself, so
    a table it finds can hold rows that it did not create. Dropping such a
    table would destroy data during a rollback, so the downgrade stops with an
    actionable message instead.
    """
    if table not in _existing_tables():
        return
    rows = _row_count(table)
    if rows:
        raise RuntimeError(
            f"Refusing to drop the table '{table}': it still holds {rows} row(s). "
            f"Export the data and drop the table yourself, or re-stamp the "
            f"revision with `alembic stamp`."
        )
    for index in sorted(_existing_indexes(table)):
        op.drop_index(index, table_name=table)
    op.drop_table(table)


def upgrade() -> None:
    """Upgrade schema."""
    tables = _existing_tables()

    if "training_runs" not in tables:
        op.create_table(
            "training_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("dataset_source", sa.String(), nullable=False),
            sa.Column("dataset_tag", sa.String(), nullable=False),
            sa.Column("hf_dataset_url", sa.String(), nullable=True),
            sa.Column("mode", sa.String(), nullable=False),
            sa.Column("env_id", sa.String(), nullable=True),
            sa.Column("optimize_metric", sa.String(), nullable=True),
            sa.Column("model_candidates", sa.JSON(), nullable=True),
            sa.Column("hyperparameters", sa.JSON(), nullable=False),
            sa.Column("metrics", sa.JSON(), nullable=True),
            sa.Column("artifact_path", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_training_runs_id"), "training_runs", ["id"], unique=False
        )
    else:
        # The table exists but may come from an older version of the
        # application: add the columns it is missing instead of accepting a
        # schema the application cannot use.
        present = _existing_columns("training_runs")
        for name, column_type, nullable, server_default in _TRAINING_RUNS_COLUMNS:
            if name in present:
                continue
            op.add_column(
                "training_runs",
                sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=server_default,
                ),
            )

    # The indexes are created independently of the table: a database that was
    # created by ``create_all`` already has the table but not the owner index.
    _create_index_if_missing(
        op.f("ix_training_runs_owner_id"), "training_runs", ["owner_id"]
    )

    if "notes" in tables:
        if op.f("ix_notes_id") in _existing_indexes("notes"):
            op.drop_index(op.f("ix_notes_id"), table_name="notes")
        op.drop_table("notes")


def downgrade() -> None:
    """Downgrade schema."""
    # ``notes`` is not restored: the chain only ever removed it, and a
    # database that never had it must not get one.
    _drop_table_if_empty("training_runs")
