"""sessions: the refresh tokens of the browser (plan A2)

Revision ID: b1d7f3e5c9a1
Revises: a9c4f0e1b2d3
Create Date: 2026-10-26 14:00:00.000000

The second half of section A2: the access token becomes short (15 minutes by
default) and the session lives in a refresh token that can be rotated and
revoked. The row holds the sha256 of the token, the family it belongs to (a
reuse of an already-rotated token revokes the family), the expiry, and the
link to its replacement.

Every column except ``user_id``/``token_hash``/``family_id``/``expires_at`` is
nullable, so the downgrade is a simple drop and the upgrade touches nothing
else.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1d7f3e5c9a1"
down_revision: Union[str, Sequence[str], None] = "a9c4f0e1b2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("family_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_id", "refresh_tokens", ["id"])
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
