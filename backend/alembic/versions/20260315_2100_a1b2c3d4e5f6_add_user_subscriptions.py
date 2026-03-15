"""Add user_subscriptions table for tier and quota tracking.

Revision ID: a1b2c3d4e5f6
Revises: f5a6b7c8d9e2
Create Date: 2026-03-15 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f5a6b7c8d9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(255), nullable=False, unique=True),
        sa.Column("tier", sa.String(50), nullable=False, server_default="starter"),
        sa.Column("strategic_queries_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strategic_queries_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_subscriptions")
