"""add notification_preferences table

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-04-04

Add notification_preferences table for per-user email notification settings.
"""

import sqlalchemy as sa
from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("org_id", sa.String(255), nullable=False),
        sa.Column("task_assigned", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("task_completed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deadline_reminder", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deadline_reminder_days", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("daily_digest", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "org_id", name="uq_notification_prefs_user_org"),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
