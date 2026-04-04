"""add action item assignment fields

Revision ID: a4b5c6d7e8f9
Revises: f1a2b3c4d5e6
Create Date: 2026-04-04

Add team assignment, notes, source tracking, and manual creation support
to action_items. Make document_id nullable for manual items.
"""

import sqlalchemy as sa
from alembic import op

revision = "a4b5c6d7e8f9"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("action_items", sa.Column("assigned_to", sa.String(255), nullable=True))
    op.add_column("action_items", sa.Column("assigned_to_name", sa.String(255), nullable=True))
    op.add_column("action_items", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("action_items", sa.Column("created_by", sa.String(255), nullable=True))
    op.add_column(
        "action_items",
        sa.Column("source", sa.String(20), nullable=False, server_default="ai_extracted"),
    )
    op.alter_column("action_items", "document_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column("action_items", "document_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("action_items", "source")
    op.drop_column("action_items", "created_by")
    op.drop_column("action_items", "notes")
    op.drop_column("action_items", "assigned_to_name")
    op.drop_column("action_items", "assigned_to")
