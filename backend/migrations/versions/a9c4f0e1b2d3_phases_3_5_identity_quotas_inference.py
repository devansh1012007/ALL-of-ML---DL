"""phases 3-5: identity, quotas, inference v2 and the honest evaluation

Revision ID: a9c4f0e1b2d3
Revises: e8f2a6c1b94d
Create Date: 2026-10-26 12:00:00.000000

The migration of the phases 3 to 5 plan (against the pasted plan of
25 October 2026):

* **identity (A1/A2)**: ``users.status`` (pending/active/suspended),
  ``token_version`` (the cheapest correct revocation), ``email``,
  ``created_at``, ``last_login_at`` and ``quota_profile_id``; the
  ``invites`` table of the invitation registration mode.
* **quotas (A3/A5)**: ``quota_profiles`` and ``user_quota_overrides`` (the
  limits are data an admin edits, NULL means unlimited), and the usage
  accounting columns of ``training_runs`` (``wall_seconds``,
  ``cpu_seconds``, ``peak_rss_bytes``, ``artifact_bytes``,
  ``artifact_sha256``, ``attempts``).
* **the audit trail (A9)**: ``audit_events``.
* **inference v2 (D1/D2/D6)**: ``deployments``, ``deployment_events``,
  ``api_keys`` and ``deployment_stats``.
* **the run view (E1/E4/E5)**: ``charts`` (the heavy data the list never
  returns), ``dataset_id`` (the comparability guard), the editable
  ``tags``/``note`` and ``job_kind`` (a queued batch prediction).

Every new column is nullable or carries a server default, so the rows of an
older version stay valid and the downgrade is a drop.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a9c4f0e1b2d3"
down_revision: Union[str, Sequence[str], None] = "e8f2a6c1b94d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _quota_columns():
    return [
        sa.Column("max_concurrent_runs", sa.Integer(), nullable=True),
        sa.Column("max_queued_runs", sa.Integer(), nullable=True),
        sa.Column("max_runs_per_day", sa.Integer(), nullable=True),
        sa.Column("max_run_seconds", sa.Integer(), nullable=True),
        sa.Column("max_run_memory_mb", sa.Integer(), nullable=True),
        sa.Column("max_cpu_seconds_per_month", sa.Integer(), nullable=True),
        sa.Column("max_storage_bytes", sa.Integer(), nullable=True),
        sa.Column("max_datasets", sa.Integer(), nullable=True),
        sa.Column("max_upload_bytes", sa.Integer(), nullable=True),
        sa.Column("max_rows", sa.Integer(), nullable=True),
        sa.Column("max_predict_rows_per_request", sa.Integer(), nullable=True),
        sa.Column("max_predict_requests_per_minute", sa.Integer(), nullable=True),
        sa.Column("allowed_categories", sa.JSON(), nullable=True),
        sa.Column("gpu_allowed", sa.Boolean(), nullable=True),
    ]


def upgrade() -> None:
    # --- users: the lifecycle, the revocation and the profile (A1/A2/A3)
    op.add_column(
        "users", sa.Column("status", sa.String(), nullable=False, server_default="active")
    )
    op.add_column(
        "users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    op.add_column("users", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("quota_profile_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_quota_profile_id", "users", ["quota_profile_id"])

    # --- the quota tables (A3)
    op.create_table(
        "quota_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        *_quota_columns(),
    )
    op.create_index("ix_quota_profiles_id", "quota_profiles", ["id"])
    op.create_index("ix_quota_profiles_name", "quota_profiles", ["name"], unique=True)

    op.create_table(
        "user_quota_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        *_quota_columns(),
    )
    op.create_index("ix_user_quota_overrides_id", "user_quota_overrides", ["id"])
    op.create_index(
        "ix_user_quota_overrides_user_id", "user_quota_overrides", ["user_id"], unique=True
    )

    # --- the invites of the invitation mode (A1)
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_invites_id", "invites", ["id"])
    op.create_index("ix_invites_code_hash", "invites", ["code_hash"])

    # --- the audit trail (A9)
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_events_id", "audit_events", ["id"])
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    # --- the deployments and the API keys (D1/D2)
    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("training_runs.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deployments_id", "deployments", ["id"])
    op.create_index("ix_deployments_owner_id", "deployments", ["owner_id"])
    op.create_index(
        "uq_deployments_owner_name", "deployments", ["owner_id", "name"], unique=True
    )

    op.create_table(
        "deployment_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "deployment_id", sa.Integer(), sa.ForeignKey("deployments.id"), nullable=False
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("from_run_id", sa.Integer(), nullable=True),
        sa.Column("to_run_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deployment_events_id", "deployment_events", ["id"])
    op.create_index(
        "ix_deployment_events_deployment_id", "deployment_events", ["deployment_id"]
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_id", "api_keys", ["id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    # --- the monitoring counters (D6)
    op.create_table(
        "deployment_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "deployment_id", sa.Integer(), sa.ForeignKey("deployments.id"), nullable=False
        ),
        sa.Column("hour", sa.String(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("out_of_range", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prediction_histogram", sa.JSON(), nullable=True),
        sa.Column("drift_flag", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_deployment_stats_id", "deployment_stats", ["id"])
    op.create_index("ix_deployment_stats_deployment_id", "deployment_stats", ["deployment_id"])
    op.create_index("ix_deployment_stats_hour", "deployment_stats", ["hour"])

    # --- the datasets: the kind and the content hash (E4/F1)
    op.add_column(
        "datasets", sa.Column("kind", sa.String(), nullable=False, server_default="tabular")
    )
    op.add_column("datasets", sa.Column("content_sha256", sa.String(), nullable=True))

    # --- the runs: the charts, the comparability, the memory, the accounting
    op.add_column("training_runs", sa.Column("dataset_id", sa.Integer(), nullable=True))
    op.add_column("training_runs", sa.Column("charts", sa.JSON(), nullable=True))
    op.add_column("training_runs", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("training_runs", sa.Column("note", sa.Text(), nullable=True))
    op.add_column("training_runs", sa.Column("artifact_sha256", sa.String(), nullable=True))
    op.add_column("training_runs", sa.Column("artifact_bytes", sa.Integer(), nullable=True))
    op.add_column(
        "training_runs", sa.Column("job_kind", sa.String(), nullable=False, server_default="train")
    )
    op.add_column("training_runs", sa.Column("wall_seconds", sa.Integer(), nullable=True))
    op.add_column("training_runs", sa.Column("cpu_seconds", sa.Integer(), nullable=True))
    op.add_column("training_runs", sa.Column("peak_rss_bytes", sa.Integer(), nullable=True))
    op.add_column(
        "training_runs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_index("ix_training_runs_dataset_id", "training_runs", ["dataset_id"])
    op.create_index("ix_training_runs_owner_created", "training_runs", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_training_runs_owner_created", table_name="training_runs")
    op.drop_index("ix_training_runs_dataset_id", table_name="training_runs")
    op.drop_index("ix_training_runs_dataset_id", table_name="training_runs")
    for column in (
        "attempts", "peak_rss_bytes", "cpu_seconds", "wall_seconds", "job_kind",
        "artifact_bytes", "artifact_sha256", "note", "tags", "charts", "dataset_id",
    ):
        op.drop_column("training_runs", column)

    op.drop_column("datasets", "content_sha256")
    op.drop_column("datasets", "kind")

    op.drop_table("deployment_stats")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("deployment_events")
    op.drop_index("uq_deployments_owner_name", table_name="deployments")
    op.drop_table("deployments")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("invites")

    op.drop_index("ix_users_quota_profile_id", table_name="users")
    for column in (
        "quota_profile_id", "last_login_at", "created_at", "email",
        "token_version", "status",
    ):
        op.drop_column("users", column)

    op.drop_index("ix_user_quota_overrides_user_id", table_name="user_quota_overrides")
    op.drop_table("user_quota_overrides")
    op.drop_index("ix_quota_profiles_name", table_name="quota_profiles")
    op.drop_table("quota_profiles")
