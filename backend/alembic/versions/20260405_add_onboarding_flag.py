"""add has_completed_onboarding to user_subscriptions

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-04-05

Track whether a user has completed the onboarding wizard.
Existing users are marked as completed (they don't need onboarding).
"""

import sqlalchemy as sa
from alembic import op

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_subscriptions",
        sa.Column(
            "has_completed_onboarding",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Existing users are not new — mark them as onboarded
    op.execute("UPDATE user_subscriptions SET has_completed_onboarding = true")


def downgrade() -> None:
    op.drop_column("user_subscriptions", "has_completed_onboarding")
