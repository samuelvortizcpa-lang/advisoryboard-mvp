"""Add token_usage table for AI API call tracking.

Revision ID: f5a6b7c8d9e2
Revises: e5f6a7b8c9d1
Create Date: 2026-03-15 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "f5a6b7c8d9e2"
down_revision = "e5f6a7b8c9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "token_usage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("query_type", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("endpoint", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_token_usage_user_created", "token_usage", ["user_id", "created_at"])
    op.create_index("ix_token_usage_client_id", "token_usage", ["client_id"])
    op.create_index("ix_token_usage_model", "token_usage", ["model"])


def downgrade() -> None:
    op.drop_index("ix_token_usage_model", table_name="token_usage")
    op.drop_index("ix_token_usage_client_id", table_name="token_usage")
    op.drop_index("ix_token_usage_user_created", table_name="token_usage")
    op.drop_table("token_usage")
