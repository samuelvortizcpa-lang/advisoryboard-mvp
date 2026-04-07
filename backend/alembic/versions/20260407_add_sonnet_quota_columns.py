"""Add sonnet_queries_limit and sonnet_queries_used columns to user_subscriptions.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_subscriptions",
        sa.Column(
            "sonnet_queries_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "user_subscriptions",
        sa.Column(
            "sonnet_queries_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_subscriptions", "sonnet_queries_used")
    op.drop_column("user_subscriptions", "sonnet_queries_limit")
