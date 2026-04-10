"""Add JSONB metadata column to document_chunks.

Stores per-chunk metadata such as voucher detection flags.
NULL by default — only populated when there's something to store.

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c3d4e5f6g7h8"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("chunk_metadata", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "chunk_metadata")
