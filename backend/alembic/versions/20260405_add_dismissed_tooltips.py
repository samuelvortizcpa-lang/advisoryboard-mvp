"""add dismissed_tooltips to user_subscriptions

Revision ID: e8f9a0b1c2d3
Revises: c6d7e8f9a0b1
Create Date: 2026-04-05

Track which contextual tooltips the user has dismissed.
"""

import sqlalchemy as sa
from alembic import op

revision = "e8f9a0b1c2d3"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_subscriptions",
        sa.Column(
            "dismissed_tooltips",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.execute("UPDATE user_subscriptions SET dismissed_tooltips = '[]'")


def downgrade() -> None:
    op.drop_column("user_subscriptions", "dismissed_tooltips")
