"""add workflow_type to engagement_template_tasks and set quarterly estimate tasks

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-06

Adds workflow_type column to engagement_template_tasks so tasks can trigger
specialized workflows (e.g. quarterly_estimate) instead of generic emails.
Updates existing 1040 Q1-Q4 estimate prep tasks with workflow_type.
"""

import sqlalchemy as sa
from alembic import op

revision = "h8i9j0k1l2m3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "engagement_template_tasks",
        sa.Column("workflow_type", sa.String(30), nullable=True),
    )

    # Set workflow_type on existing quarterly estimate prep tasks
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE engagement_template_tasks
            SET workflow_type = 'quarterly_estimate'
            WHERE category = 'quarterly_estimate'
              AND task_name LIKE '%estimated tax prep%'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("engagement_template_tasks", "workflow_type")
