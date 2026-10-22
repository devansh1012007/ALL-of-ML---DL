"""make the name of a dataset unique per owner

Revision ID: d5e91c4a7b02
Revises: f3c8b2d6e0a1
Create Date: 2026-10-22 16:30:00.000000

The name of a dataset is what the user sees, and a name that is used twice
makes the list ambiguous: a request that names a dataset could then train on
another file than the one the user picked. The application made the name
unique before it wrote the row, but two uploads of the same name that arrive
at the same time both passed that check.

The database is the place where the uniqueness belongs, so the pair
(``owner_id``, ``name``) is unique now. The rows that carry the same name
are renamed first, so that the migration also works on a database that
already holds them.
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5e91c4a7b02"
down_revision: Union[str, Sequence[str], None] = "f3c8b2d6e0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_datasets_owner_id_name"
OLD_INDEX_NAME = "ix_datasets_owner_id_name"


def _datasets_table():
    """The table of the datasets, or None when it does not exist.

    In the offline mode (``alembic upgrade head --sql``) the live database
    cannot be inspected, so the schema of a fresh installation is assumed.
    """
    if context.is_offline_mode():
        return sa.table(
            "datasets",
            sa.column("id", sa.Integer()),
            sa.column("owner_id", sa.Integer()),
            sa.column("name", sa.String()),
        )
    inspector = sa.inspect(op.get_bind())
    if "datasets" not in set(inspector.get_table_names()):
        return None
    return sa.table(
        "datasets",
        sa.column("id", sa.Integer()),
        sa.column("owner_id", sa.Integer()),
        sa.column("name", sa.String()),
    )


def _rename_the_duplicates(table) -> None:
    """Give every row of a duplicated name its own name.

    The rows of the built-in datasets have no owner, and the rows of the
    uploads have one: a name is only ambiguous inside an owner, so the
    duplicates are looked for per owner.
    """
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(table.c.id, table.c.owner_id, table.c.name)
    ).fetchall()
    seen = set()
    for row_id, owner_id, name in rows:
        key = (owner_id, name)
        if key not in seen:
            seen.add(key)
            continue
        # The name is already taken: the row gets a suffix.
        suffix = 2
        candidate = f"{name} ({suffix})"
        while (owner_id, candidate) in seen:
            suffix += 1
            candidate = f"{name} ({suffix})"
        seen.add((owner_id, candidate))
        connection.execute(
            table.update()
            .where(table.c.id == row_id)
            .values(name=candidate)
        )


def upgrade() -> None:
    """Upgrade schema."""
    table = _datasets_table()
    if table is None:
        return

    if not context.is_offline_mode():
        _rename_the_duplicates(table)

    # The index that the previous revision created on the same columns is
    # replaced: the unique one serves the listing as well.
    op.drop_index(OLD_INDEX_NAME, table_name="datasets")
    op.create_index(INDEX_NAME, "datasets", ["owner_id", "name"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    if _datasets_table() is None:
        return

    op.drop_index(INDEX_NAME, table_name="datasets")
    op.create_index(
        OLD_INDEX_NAME, "datasets", ["owner_id", "name"], unique=False
    )
