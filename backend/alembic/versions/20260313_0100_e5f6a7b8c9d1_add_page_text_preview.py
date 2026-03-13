"""Add page_text_preview column to document_page_images.

Revision ID: e5f6a7b8c9d1
Revises: d4e5f6a7b8c0
Create Date: 2026-03-13 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d1"
down_revision = "d4e5f6a7b8c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_page_images",
        sa.Column("page_text_preview", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_page_images", "page_text_preview")
