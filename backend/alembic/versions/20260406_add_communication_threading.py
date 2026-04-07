"""Add communication threading columns.

Revision ID: g7h8i9j0k1l2
Revises: f3a4b5c6d7e8
Create Date: 2026-04-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "g7h8i9j0k1l2"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_communications", sa.Column("thread_id", UUID(as_uuid=True), nullable=True))
    op.add_column("client_communications", sa.Column("thread_type", sa.String(30), nullable=True))
    op.add_column("client_communications", sa.Column("thread_year", sa.Integer(), nullable=True))
    op.add_column("client_communications", sa.Column("thread_quarter", sa.Integer(), nullable=True))
    op.add_column("client_communications", sa.Column("open_items", JSONB, nullable=True))
    op.add_column("client_communications", sa.Column("open_items_resolved", JSONB, nullable=True))

    op.create_index(
        "ix_client_communications_thread",
        "client_communications",
        ["client_id", "thread_id"],
    )
    op.create_index(
        "ix_client_communications_thread_type_year",
        "client_communications",
        ["client_id", "thread_type", "thread_year"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_communications_thread_type_year", table_name="client_communications")
    op.drop_index("ix_client_communications_thread", table_name="client_communications")

    op.drop_column("client_communications", "open_items_resolved")
    op.drop_column("client_communications", "open_items")
    op.drop_column("client_communications", "thread_quarter")
    op.drop_column("client_communications", "thread_year")
    op.drop_column("client_communications", "thread_type")
    op.drop_column("client_communications", "thread_id")
