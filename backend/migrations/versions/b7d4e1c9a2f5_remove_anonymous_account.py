"""remove the shared anonymous account

Revision ID: b7d4e1c9a2f5
Revises: c4a9e2b17d3f
Create Date: 2026-10-22 12:00:00.000000

Until this revision, a request without an ``Authorization`` header fell back
to a shared account named ``anonymous``, whose password was literally
``anonymous``. Every unauthenticated caller shared that account's history, and
anybody could log into it with the published password.

The account is removed together with the runs that belong to it: they are the
runs of the unauthenticated callers, which are the runs of everybody, and
keeping them would leave the data of the old shared bucket behind.

The rows are deleted by their name, so the revision is safe on a database that
never had the account.
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d4e1c9a2f5"
down_revision: Union[str, Sequence[str], None] = "c4a9e2b17d3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set:
    """The tables that exist in the database the migration runs against."""
    if context.is_offline_mode():
        return frozenset({"users", "training_runs"})
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Upgrade schema."""
    tables = _existing_tables()
    if "users" not in tables:
        return

    if "training_runs" in tables:
        # The runs of the shared account are the runs of everybody: they are
        # removed with the account.
        op.execute(
            sa.text(
                "DELETE FROM training_runs WHERE owner_id IN "
                "(SELECT id FROM users WHERE username = 'anonymous')"
            )
        )
    op.execute(sa.text("DELETE FROM users WHERE username = 'anonymous'"))


def downgrade() -> None:
    """Downgrade schema.

    The shared account is not restored: recreating it with a published
    password would reintroduce the vulnerability this revision removes.
    """
    return
