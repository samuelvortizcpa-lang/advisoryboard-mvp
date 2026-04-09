"""Backfill search_vector for existing document_chunks.

Revision ID: b2c3d4e5f6g7
Revises: e4f5g6h7i8j9
Create Date: 2026-04-09
"""
from alembic import op

revision = 'b2c3d4e5f6g7'
down_revision = 'e4f5g6h7i8j9'
branch_labels = None
depends_on = None

def upgrade():
    # Already applied — backfilled search_vector tsvector column on document_chunks
    pass

def downgrade():
    pass
