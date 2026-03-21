"""add_esignature_fields_to_client_consents

Revision ID: d348e822f38f
Revises: f5207c80df1c
Create Date: 2026-03-21 17:43:48.859873+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = 'd348e822f38f'
down_revision: Union[str, None] = 'f5207c80df1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('client_consents', sa.Column('signing_token', sa.String(length=64), nullable=True))
    op.add_column('client_consents', sa.Column('signing_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('client_consents', sa.Column('sent_to_email', sa.String(), nullable=True))
    op.add_column('client_consents', sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('client_consents', sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('client_consents', sa.Column('signer_ip_address', sa.String(), nullable=True))
    op.add_column('client_consents', sa.Column('signer_user_agent', sa.Text(), nullable=True))
    op.add_column('client_consents', sa.Column('signer_typed_name', sa.String(), nullable=True))
    op.add_column('client_consents', sa.Column('signed_pdf_url', sa.String(), nullable=True))
    op.create_index(op.f('ix_client_consents_signing_token'), 'client_consents', ['signing_token'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_client_consents_signing_token'), table_name='client_consents')
    op.drop_column('client_consents', 'signed_pdf_url')
    op.drop_column('client_consents', 'signer_typed_name')
    op.drop_column('client_consents', 'signer_user_agent')
    op.drop_column('client_consents', 'signer_ip_address')
    op.drop_column('client_consents', 'signed_at')
    op.drop_column('client_consents', 'sent_at')
    op.drop_column('client_consents', 'sent_to_email')
    op.drop_column('client_consents', 'signing_token_expires_at')
    op.drop_column('client_consents', 'signing_token')
