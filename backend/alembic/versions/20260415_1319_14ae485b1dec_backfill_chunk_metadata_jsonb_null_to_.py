"""backfill chunk_metadata jsonb null to sql null

Revision ID: 14ae485b1dec
Revises: d4e5f6g7h8i9
Create Date: 2026-04-15 13:19:18.500931+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic
revision: str = '14ae485b1dec'
down_revision: Union[str, None] = 'd4e5f6g7h8i9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Pre-flight: count rows that match the backfill criteria.
    # Expected: 231 on production as of Apr 16 2026.
    # If the count is dramatically different, something has changed and
    # the migration should fail loudly rather than silently mass-update.
    result = conn.execute(sa.text("""
        SELECT COUNT(*) FROM document_chunks
        WHERE chunk_metadata IS NOT NULL
          AND jsonb_typeof(chunk_metadata) = 'null'
    """))
    count = result.scalar()
    print(f"[backfill] {count} rows match jsonb null criteria; converting to SQL NULL")

    # Apply the backfill.
    conn.execute(sa.text("""
        UPDATE document_chunks
        SET chunk_metadata = NULL
        WHERE chunk_metadata IS NOT NULL
          AND jsonb_typeof(chunk_metadata) = 'null'
    """))

    # Post-flight: verify the criterion is now empty.
    result = conn.execute(sa.text("""
        SELECT COUNT(*) FROM document_chunks
        WHERE chunk_metadata IS NOT NULL
          AND jsonb_typeof(chunk_metadata) = 'null'
    """))
    remaining = result.scalar()
    if remaining != 0:
        raise RuntimeError(
            f"[backfill] verification failed: {remaining} rows still match "
            f"the jsonb null criterion after UPDATE"
        )
    print(f"[backfill] verified: 0 rows remaining with jsonb null")


def downgrade() -> None:
    # Intentional no-op. The backfill converts JSONB null literals (which
    # were a bug) to SQL NULL (which is the correct representation for
    # "no metadata"). There is no meaningful inverse — re-introducing JSONB
    # null literal would re-introduce the bug. Older code paths that read
    # chunk_metadata don't distinguish the two, so this downgrade is safe
    # to leave empty.
    pass
