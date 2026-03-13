"""Add document_page_images table for multimodal RAG.

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f6a7b9
Create Date: 2026-03-12 24:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c0"
down_revision = "c3d4e5f6a7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create table without the vector column first (added via raw SQL)
    op.create_table(
        "document_page_images",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Add the pgvector column (768 dims for Gemini embeddings)
    op.execute(
        "ALTER TABLE document_page_images "
        "ADD COLUMN image_embedding vector(768)"
    )

    # Index on document_id for cascading lookups
    op.create_index(
        "ix_document_page_images_document_id",
        "document_page_images",
        ["document_id"],
    )

    # HNSW index for fast approximate nearest-neighbor search on embeddings
    op.execute(
        "CREATE INDEX ix_document_page_images_embedding "
        "ON document_page_images USING hnsw (image_embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_page_images_embedding")
    op.drop_table("document_page_images")
