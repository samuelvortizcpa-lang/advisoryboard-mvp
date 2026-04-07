"""add engagement_task_id to action_items

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-04-06

Links action items to the engagement template task that generated them,
preventing duplicate auto-generation.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "action_items",
        sa.Column(
            "engagement_task_id",
            sa.UUID(),
            sa.ForeignKey("engagement_template_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_action_item_engagement_task",
        "action_items",
        ["client_id", "engagement_task_id", "due_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_action_item_engagement_task", "action_items")
    op.drop_column("action_items", "engagement_task_id")
