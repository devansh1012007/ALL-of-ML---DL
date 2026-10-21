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
every step is guarded by the table list of the live database.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4a9e2b17d3f"
down_revision: Union[str, Sequence[str], None] = "7f9590585a2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set:
    """The tables that exist in the database the migration runs against."""
    return set(sa.inspect(op.get_bind()).get_table_names())


def _existing_indexes(table: str) -> set:
    """The names of the indexes of ``table``."""
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table)}


def _create_index_if_missing(name: str, table: str, columns) -> None:
    """Create an index unless the table already carries it.

    A database that was created by ``create_all`` before the owner index was
    added to the ORM has the table but not the index, so the index is checked
    independently of the table.
    """
    if name not in _existing_indexes(table):
        op.create_index(name, table, columns, unique=False)


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

    # The indexes are created independently of the table: a database that was
    # created by ``create_all`` already has the table but not the owner index.
    _create_index_if_missing(
        op.f("ix_training_runs_owner_id"), "training_runs", ["owner_id"]
    )

    if "notes" in tables:
        op.drop_index(op.f("ix_notes_id"), table_name="notes")
        op.drop_table("notes")


def downgrade() -> None:
    """Downgrade schema."""
    tables = _existing_tables()

    if "notes" not in tables:
        op.create_table(
            "notes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("content", sa.String(), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_notes_id"), "notes", ["id"], unique=False)

    if "training_runs" in tables:
        op.drop_index(op.f("ix_training_runs_owner_id"), table_name="training_runs")
        op.drop_index(op.f("ix_training_runs_id"), table_name="training_runs")
        op.drop_table("training_runs")
