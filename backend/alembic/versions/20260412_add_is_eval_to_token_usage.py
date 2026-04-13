"""Add is_eval boolean column to token_usage.

Allows quota enforcement to exclude eval-framework traffic while still
recording it for cost attribution.

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-04-12
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6g7h8i9"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "token_usage",
        sa.Column("is_eval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(
        "ix_token_usage_user_is_eval",
        "token_usage",
        ["user_id", "is_eval"],
    )


def downgrade() -> None:
    op.drop_index("ix_token_usage_user_is_eval", table_name="token_usage")
    op.drop_column("token_usage", "is_eval")
