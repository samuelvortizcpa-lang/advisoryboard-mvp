"""Add tsvector search_vector column to document_chunks for full-text search.

Revision ID: r3s4t5u6v7w8
Revises: l2m3n4o5p6q7
Create Date: 2026-04-09
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "r3s4t5u6v7w8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add tsvector column
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN search_vector tsvector;"
    )

    # 2. Backfill existing rows
    op.execute(
        "UPDATE document_chunks SET search_vector = to_tsvector('english', COALESCE(chunk_text, ''));"
    )

    # 3. Create GIN index for fast full-text search
    op.execute(
        "CREATE INDEX idx_chunks_search_vector ON document_chunks USING GIN(search_vector);"
    )

    # 4. Create trigger to auto-populate search_vector on insert/update
    op.execute("""
        CREATE OR REPLACE FUNCTION update_chunk_search_vector()
        RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := to_tsvector('english', COALESCE(NEW.chunk_text, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_update_search_vector
        BEFORE INSERT OR UPDATE OF chunk_text ON document_chunks
        FOR EACH ROW EXECUTE FUNCTION update_chunk_search_vector();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_update_search_vector ON document_chunks;")
    op.execute("DROP FUNCTION IF EXISTS update_chunk_search_vector();")
    op.execute("DROP INDEX IF EXISTS idx_chunks_search_vector;")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS search_vector;")
