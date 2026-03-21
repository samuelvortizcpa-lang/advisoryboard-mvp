"""add_7216_consent_tracking

Revision ID: f5207c80df1c
Revises: f4c21e7bad46
Create Date: 2026-03-21 17:15:07.161168+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = 'f5207c80df1c'
down_revision: Union[str, None] = 'f4c21e7bad46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('client_consents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('client_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('consent_type', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('consent_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expiration_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('consent_method', sa.String(), nullable=True),
    sa.Column('taxpayer_name', sa.String(), nullable=True),
    sa.Column('preparer_name', sa.String(), nullable=True),
    sa.Column('preparer_firm', sa.String(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('form_generated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_client_consents_client_id'), 'client_consents', ['client_id'], unique=False)
    op.create_index(op.f('ix_client_consents_user_id'), 'client_consents', ['user_id'], unique=False)
    op.add_column('clients', sa.Column('consent_status', sa.String(length=50), server_default='not_required', nullable=False))
    op.add_column('clients', sa.Column('has_tax_documents', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('clients', 'has_tax_documents')
    op.drop_column('clients', 'consent_status')
    op.drop_index(op.f('ix_client_consents_user_id'), table_name='client_consents')
    op.drop_index(op.f('ix_client_consents_client_id'), table_name='client_consents')
    op.drop_table('client_consents')
