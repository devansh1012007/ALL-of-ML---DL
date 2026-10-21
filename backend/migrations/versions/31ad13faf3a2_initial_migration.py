"""initial migration

Revision ID: 31ad13faf3a2
Revises:
Create Date: 2026-03-25 18:02:10.464863

Note (2026-10-22): the DDL of this revision is guarded by the table list of
the live database. Until the schema was owned by the migrations, the
application created the tables itself (``Base.metadata.create_all``), so a
developer database can already contain ``users`` (and later ``training_runs``)
without ever having an ``alembic_version`` row. An unguarded revision fails on
such a database with ``DuplicateTableError`` before it can reach the revision
that repairs it, so the guard is what makes ``alembic upgrade head`` work on
every database that exists in the wild.

The downgrade refuses to drop a table that still holds rows: a rollback must
not destroy data that this chain did not create.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31ad13faf3a2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The schema of a fresh database before this revision, used in offline mode
# (``alembic upgrade head --sql``), where the live database cannot be
# inspected. The offline SQL is the DDL of a fresh installation.
_TABLES_BEFORE = frozenset()
_INDEXES_BEFORE = {"users": frozenset(), "notes": frozenset()}


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


def _row_count(table: str) -> int:
    """The number of rows of ``table``."""
    return op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM "{table}"')).scalar() or 0


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

    if 'users' not in tables:
        op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
        op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    if 'notes' not in tables:
        op.create_table('notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('content', sa.String(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_notes_id'), 'notes', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    _drop_table_if_empty('notes')
    _drop_table_if_empty('users')
