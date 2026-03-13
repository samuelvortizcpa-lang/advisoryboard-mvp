"""add_document_intelligence

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-03-12 21:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Document classification fields
    op.add_column(
        'documents',
        sa.Column('document_type', sa.String(50), nullable=True),
    )
    op.add_column(
        'documents',
        sa.Column('document_subtype', sa.String(100), nullable=True),
    )
    op.add_column(
        'documents',
        sa.Column('document_period', sa.String(20), nullable=True),
    )
    op.add_column(
        'documents',
        sa.Column('classification_confidence', sa.Float, nullable=True),
    )

    # Versioning fields
    op.add_column(
        'documents',
        sa.Column(
            'superseded_by',
            UUID(as_uuid=True),
            sa.ForeignKey('documents.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )
    op.add_column(
        'documents',
        sa.Column('is_superseded', sa.Boolean, server_default='false', nullable=False),
    )

    op.create_index('ix_documents_document_type', 'documents', ['document_type'])
    op.create_index('ix_documents_is_superseded', 'documents', ['is_superseded'])


def downgrade() -> None:
    op.drop_index('ix_documents_is_superseded', table_name='documents')
    op.drop_index('ix_documents_document_type', table_name='documents')
    op.drop_column('documents', 'is_superseded')
    op.drop_column('documents', 'superseded_by')
    op.drop_column('documents', 'classification_confidence')
    op.drop_column('documents', 'document_period')
    op.drop_column('documents', 'document_subtype')
    op.drop_column('documents', 'document_type')
