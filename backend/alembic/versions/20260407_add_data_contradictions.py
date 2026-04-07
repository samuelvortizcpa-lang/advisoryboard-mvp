"""Add data_contradictions table for contradiction detection.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_contradictions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contradiction_type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("value_a", sa.Numeric(15, 2), nullable=True),
        sa.Column("value_b", sa.Numeric(15, 2), nullable=True),
        sa.Column("source_a_type", sa.String(30), nullable=True),
        sa.Column("source_a_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_a_label", sa.String(200), nullable=True),
        sa.Column("source_b_type", sa.String(30), nullable=True),
        sa.Column("source_b_id", UUID(as_uuid=True), nullable=True),
        sa.Column("source_b_label", sa.String(200), nullable=True),
        sa.Column("tax_year", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_data_contradictions_client_status", "data_contradictions", ["client_id", "status"])
    op.create_index("ix_data_contradictions_client_tax_year", "data_contradictions", ["client_id", "tax_year"])
    op.create_index("ix_data_contradictions_severity", "data_contradictions", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_data_contradictions_severity", table_name="data_contradictions")
    op.drop_index("ix_data_contradictions_client_tax_year", table_name="data_contradictions")
    op.drop_index("ix_data_contradictions_client_status", table_name="data_contradictions")
    op.drop_table("data_contradictions")
