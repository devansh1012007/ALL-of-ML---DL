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
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31ad13faf3a2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set:
    """The tables that exist in the database the migration runs against."""
    return set(sa.inspect(op.get_bind()).get_table_names())


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
    tables = _existing_tables()

    if 'notes' in tables:
        op.drop_index(op.f('ix_notes_id'), table_name='notes')
        op.drop_table('notes')

    if 'users' in tables:
        op.drop_index(op.f('ix_users_username'), table_name='users')
        op.drop_index(op.f('ix_users_id'), table_name='users')
        op.drop_table('users')
