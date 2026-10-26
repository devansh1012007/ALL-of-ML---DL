"""the fair share, the retries and the capability routing (plans B5-B7)

Revision ID: e5a7c9d1f3b5
Revises: d4e6f8a0b2c4
Create Date: 2026-10-26 18:00:00.000000

* ``training_runs.priority`` - the claim prefers the owner with the fewest
  running runs, then the highest priority, then the oldest run (B5);
* ``training_runs.requirements`` - what the model needs (a GPU? how much
  memory?), recorded at the enqueue, checked by every claim (B7);
* ``training_runs.max_attempts`` - a run whose worker died is requeued
  while it has attempts left (B6);
* the ``workers`` table - every worker registers its capabilities and its
  heartbeat (B7).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5a7c9d1f3b5"
down_revision: Union[str, Sequence[str], None] = "d4e6f8a0b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("training_runs", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("training_runs", sa.Column("requirements", sa.JSON(), nullable=True))
    op.add_column("training_runs", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"))
    op.create_table(
        "workers",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("memory_mb", sa.Integer(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("workers")
    op.drop_column("training_runs", "max_attempts")
    op.drop_column("training_runs", "requirements")
    op.drop_column("training_runs", "priority")
