"""add_document_source

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-07 00:02:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Source of the document: 'upload', 'gmail', 'outlook', 'zoom'
    op.add_column(
        'documents',
        sa.Column('source', sa.String(20), server_default='upload', nullable=False),
    )

    # Generic external ID for deduplication across integrations
    op.add_column(
        'documents',
        sa.Column('external_id', sa.String(255), nullable=True),
    )

    op.create_index(
        'ix_documents_source', 'documents', ['source'],
    )
    op.create_unique_constraint(
        'uq_documents_client_external_id',
        'documents',
        ['client_id', 'external_id'],
    )

    # Backfill: set source='gmail' and external_id for existing Gmail-ingested docs
    op.execute("""
        UPDATE documents
        SET source = 'gmail', external_id = gmail_message_id
        WHERE gmail_message_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_constraint('uq_documents_client_external_id', 'documents', type_='unique')
    op.drop_index('ix_documents_source', table_name='documents')
    op.drop_column('documents', 'external_id')
    op.drop_column('documents', 'source')
