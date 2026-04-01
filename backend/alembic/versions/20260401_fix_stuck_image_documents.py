"""fix stuck image documents — mark as processed

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-01

Image files (PNG/JPG screenshots from extension) don't have extractable text.
The processing pipeline raised UnsupportedFileType, leaving them stuck with
processed=False. This migration marks existing image documents as processed.
"""

from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE documents
        SET processed = true, processing_error = NULL
        WHERE processed = false
          AND (
            file_type IN ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff')
            OR filename ILIKE '%.png'
            OR filename ILIKE '%.jpg'
            OR filename ILIKE '%.jpeg'
          )
    """)


def downgrade() -> None:
    pass
