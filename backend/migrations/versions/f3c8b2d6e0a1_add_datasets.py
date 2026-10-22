"""add the datasets table

Revision ID: f3c8b2d6e0a1
Revises: b7d4e1c9a2f5
Create Date: 2026-10-22 14:00:00.000000

The registry replaces the "the client sends a file name, the server turns it
into a path" convention. A dataset is a row, and only the server turns a row
into a path: the path is relative to the datasets root, so a dataset can
never point outside of it.

``owner_id`` is NULL for the datasets that ship with the repository - they
belong to everybody - and set for the uploaded ones.
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3c8b2d6e0a1"
down_revision: Union[str, Sequence[str], None] = "b7d4e1c9a2f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set:
    """The tables that exist in the database the migration runs against.

    In the offline mode (``alembic upgrade head --sql``) the live database
    cannot be inspected, so the schema of a fresh installation is assumed.
    """
    if context.is_offline_mode():
        return frozenset({"users", "training_runs"})
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Upgrade schema."""
    if "datasets" in _existing_tables():
        return

    op.create_table(
        "datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("columns", sa.JSON(), nullable=True),
        sa.Column("label_column", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_datasets_id"), "datasets", ["id"], unique=False)
    op.create_index(
        op.f("ix_datasets_owner_id"), "datasets", ["owner_id"], unique=False
    )
    # The path of a dataset is unique: it is what identifies the file.
    op.create_index(
        op.f("ix_datasets_storage_path"), "datasets", ["storage_path"], unique=True
    )
    # The listing is always "the datasets of this owner, by name", so the pair
    # is indexed.
    op.create_index(
        op.f("ix_datasets_owner_id_name"), "datasets", ["owner_id", "name"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    if "datasets" not in _existing_tables():
        return

    op.drop_index(op.f("ix_datasets_owner_id_name"), table_name="datasets")
    op.drop_index(op.f("ix_datasets_storage_path"), table_name="datasets")
    op.drop_index(op.f("ix_datasets_owner_id"), table_name="datasets")
    op.drop_index(op.f("ix_datasets_id"), table_name="datasets")
    op.drop_table("datasets")
