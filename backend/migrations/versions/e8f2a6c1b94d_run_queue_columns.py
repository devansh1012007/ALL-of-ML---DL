"""make the training runs a queue: request, heartbeat, worker, timestamps

Revision ID: e8f2a6c1b94d
Revises: d5e91c4a7b02
Create Date: 2026-10-25 12:00:00.000000

A run used to live in the memory of the process that started it: the
parameters of the request were a closure of a background task, so a restart
lost every queued run, and the only way to find out that a worker had died was
to fail every queued or running row at startup (which is wrong as soon as a
second process runs).

The row is the queue now:

* ``request_payload`` holds everything the worker needs, so a queued run
  survives a restart and any process can pick it up;
* ``worker_id``, ``started_at`` and ``heartbeat_at`` say who runs a run and
  that it is still alive: a running run whose heartbeat stopped is failed, a
  running run whose heartbeat is fresh is left alone;
* ``finished_at`` closes the interval (the duration of a run);
* ``status`` is indexed because the worker asks for the oldest queued run.

Every column is nullable: the rows of an older version stay valid. A queued
run without a request cannot be resumed and is failed with a message.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8f2a6c1b94d"
down_revision: Union[str, Sequence[str], None] = "d5e91c4a7b02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("training_runs", sa.Column("request_payload", sa.JSON(), nullable=True))
    op.add_column("training_runs", sa.Column("worker_id", sa.String(), nullable=True))
    op.add_column(
        "training_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "training_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "training_runs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_training_runs_status", "training_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_training_runs_status", table_name="training_runs")
    with op.batch_alter_table("training_runs") as batch:
        batch.drop_column("finished_at")
        batch.drop_column("heartbeat_at")
        batch.drop_column("started_at")
        batch.drop_column("worker_id")
        batch.drop_column("request_payload")
