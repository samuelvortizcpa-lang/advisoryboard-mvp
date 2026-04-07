"""add client_financial_metrics table

Revision ID: b7c8d9e0f1a2
Revises: f9a0b1c2d3e4
Create Date: 2026-04-06

Stores structured financial data extracted from client documents
(tax returns, financial statements) for trend analysis and
enriched AI context.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_financial_metrics",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id",
            sa.UUID(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column("metric_category", sa.String(50), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Numeric(15, 2), nullable=True),
        sa.Column("form_source", sa.String(50), nullable=True),
        sa.Column("line_reference", sa.String(50), nullable=True),
        sa.Column(
            "is_amended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "confidence",
            sa.Numeric(3, 2),
            nullable=False,
            server_default=sa.text("1.00"),
        ),
        sa.UniqueConstraint(
            "client_id",
            "tax_year",
            "metric_name",
            "form_source",
            name="uq_client_financial_metric",
        ),
    )


def downgrade() -> None:
    op.drop_table("client_financial_metrics")
