"""Add HNSW index on document_chunks.embedding for vector similarity search.

Without this index, every RAG query does a full sequential scan across all
chunks for a client using cosine_distance(). The HNSW index enables
approximate nearest neighbor search, reducing query time from O(n) to
O(log n).

Revision ID: a1b2c3d4e5f8
Revises: e9f0a1b2c3d4
Create Date: 2026-03-28
"""

from typing import Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # HNSW index for cosine distance similarity search.
    # vector_cosine_ops matches the cosine_distance() operator used in
    # rag_service.py queries.
    #
    # m=16, ef_construction=64 are pgvector defaults — good balance of
    # build time, index size, and recall for datasets under ~1M vectors.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
