"""phases 6: the rate limiter moves to the database (plan A8)

Revision ID: b8c2d4e6f0a2
Revises: b1d7f3e5c9a1
Create Date: 2026-10-26 15:00:00.000000

A limiter that lives in the memory of a process is a lie the moment a second
worker starts. ``rate_events`` holds one row per counted attempt, and the
count of a key inside the window is a single query - shared by every worker
of the deployment. Rows older than the window are purged by the maintenance
loop, so the table stays small.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8c2d4e6f0a2"
down_revision: Union[str, Sequence[str], None] = "b1d7f3e5c9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rate_events_id", "rate_events", ["id"])
    op.create_index("ix_rate_events_key", "rate_events", ["key"])
    op.create_index("ix_rate_events_at", "rate_events", ["at"])


def downgrade() -> None:
    op.drop_index("ix_rate_events_at", table_name="rate_events")
    op.drop_index("ix_rate_events_key", table_name="rate_events")
    op.drop_index("ix_rate_events_id", table_name="rate_events")
    op.drop_table("rate_events")
