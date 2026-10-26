"""progress events: the run_events table (plan B4)

Revision ID: d4e6f8a0b2c4
Revises: c3e5f7a9d1b3
Create Date: 2026-10-26 17:00:00.000000

A run must report what it is doing. ``run_events`` is the stream: the phases,
the epochs, the metrics and the log lines of one run, ordered by ``seq``,
polled by ``GET /runs/{id}/events?after=`` and streamed by
``GET /runs/{id}/stream``.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e6f8a0b2c4"
down_revision: Union[str, Sequence[str], None] = "c3e5f7a9d1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("training_runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
    )
    op.create_index("ix_run_events_id", "run_events", ["id"])
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_index("ix_run_events_seq", "run_events", ["seq"])


def downgrade() -> None:
    op.drop_index("ix_run_events_seq", table_name="run_events")
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_index("ix_run_events_id", table_name="run_events")
    op.drop_table("run_events")
