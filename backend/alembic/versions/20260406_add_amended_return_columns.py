"""add amended return columns to documents

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-04-06

Adds amends_subtype and amendment_number columns to support
amended tax returns (1040X, 1120X, etc.).
"""

import sqlalchemy as sa
from alembic import op

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("amends_subtype", sa.String(100), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("amendment_number", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "amendment_number")
    op.drop_column("documents", "amends_subtype")
