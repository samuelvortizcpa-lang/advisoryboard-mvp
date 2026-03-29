"""add audit_logs table

Revision ID: c8d9e0f1a2b3
Revises: a7f8b9c0d1e2
Create Date: 2026-03-29

Audit logging for compliance — tracks who accessed what data and when.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "c8d9e0f1a2b3"
down_revision = "a7f8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("detail", JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
    )

    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_org_timestamp", "audit_logs", ["org_id", "timestamp"])
    op.create_index("ix_audit_logs_user_timestamp", "audit_logs", ["user_id", "timestamp"])


def downgrade() -> None:
    op.drop_table("audit_logs")
