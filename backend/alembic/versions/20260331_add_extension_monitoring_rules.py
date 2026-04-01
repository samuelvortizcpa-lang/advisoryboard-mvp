"""add extension_monitoring_rules table

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-03-31

Browser extension monitoring rules: per-user patterns that match pages/emails
to clients and surface capture suggestions in the extension.
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"


def upgrade() -> None:
    op.create_table(
        "extension_monitoring_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", sa.String(255), nullable=False, index=True),
        sa.Column("org_id", UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("rule_name", sa.String(200), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_only", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_ext_monitoring_user_active",
        "extension_monitoring_rules",
        ["user_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_ext_monitoring_user_active", table_name="extension_monitoring_rules")
    op.drop_table("extension_monitoring_rules")
