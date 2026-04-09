"""Backfill search_vector for existing document_chunks.

Populates the tsvector column for all rows where it's currently NULL,
enabling BM25 hybrid search on pre-existing chunks.

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-09
"""

from alembic import op

revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE document_chunks "
        "SET search_vector = to_tsvector('english', COALESCE(chunk_text, '')) "
        "WHERE search_vector IS NULL"
    )


def downgrade() -> None:
    # No-op: we don't remove tsvector data on downgrade since the column
    # and trigger still exist from the earlier migration.
    pass
