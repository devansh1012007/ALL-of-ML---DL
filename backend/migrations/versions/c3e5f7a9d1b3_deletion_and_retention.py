"""deletion and retention (plan H1)

Revision ID: c3e5f7a9d1b3
Revises: b8c2d4e6f0a2
Create Date: 2026-10-26 16:00:00.000000

A user who cannot delete what they made cannot be given a storage quota: the
space never comes back. The columns here carry the two halves of H1:

* ``training_runs.artifact_removed_at`` - the moment the artifact of a run
  was removed while the run stayed (retention, or the janitor that noticed a
  missing file). The metrics survive; the heavy file does not.
* ``quota_profiles.artifact_keep_runs`` / ``artifact_keep_days`` (and the
  same two on ``user_quota_overrides``) - the retention rules an admin sets
  per profile: keep the artifacts of the last N runs, or of the last X days;
  NULL keeps everything.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3e5f7a9d1b3"
down_revision: Union[str, Sequence[str], None] = "b8c2d4e6f0a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "training_runs",
        sa.Column("artifact_removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "quota_profiles",
        sa.Column("artifact_keep_runs", sa.Integer(), nullable=True),
    )
    op.add_column(
        "quota_profiles",
        sa.Column("artifact_keep_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_quota_overrides",
        sa.Column("artifact_keep_runs", sa.Integer(), nullable=True),
    )
    op.add_column(
        "user_quota_overrides",
        sa.Column("artifact_keep_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_quota_overrides", "artifact_keep_days")
    op.drop_column("user_quota_overrides", "artifact_keep_runs")
    op.drop_column("quota_profiles", "artifact_keep_days")
    op.drop_column("quota_profiles", "artifact_keep_runs")
    op.drop_column("training_runs", "artifact_removed_at")
