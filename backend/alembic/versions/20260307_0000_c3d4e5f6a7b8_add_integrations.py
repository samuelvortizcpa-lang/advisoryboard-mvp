"""add_integrations

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-07 00:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


# revision identifiers, used by Alembic
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create integration_connections table
    op.create_table(
        'integration_connections',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_email', sa.String(255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index('ix_integration_connections_user_id', 'integration_connections', ['user_id'])
    op.create_index('ix_integration_connections_provider', 'integration_connections', ['provider'])
    op.create_unique_constraint(
        'uq_integration_connections_user_provider_email',
        'integration_connections',
        ['user_id', 'provider', 'provider_email'],
    )

    # 2. Create email_routing_rules table
    op.create_table(
        'email_routing_rules',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('email_address', sa.String(255), nullable=False),
        sa.Column(
            'client_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('clients.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('match_type', sa.String(20), server_default='from', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index('ix_email_routing_rules_user_id', 'email_routing_rules', ['user_id'])
    op.create_index('ix_email_routing_rules_email_address', 'email_routing_rules', ['email_address'])
    op.create_index('ix_email_routing_rules_client_id', 'email_routing_rules', ['client_id'])
    op.create_unique_constraint(
        'uq_email_routing_rules_user_email_match',
        'email_routing_rules',
        ['user_id', 'email_address', 'match_type'],
    )

    # 3. Create sync_logs table
    op.create_table(
        'sync_logs',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'connection_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('integration_connections.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('sync_type', sa.String(20), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('emails_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('emails_ingested', sa.Integer(), server_default='0', nullable=False),
        sa.Column('emails_skipped', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column(
            'started_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_sync_logs_connection_id', 'sync_logs', ['connection_id'])


def downgrade() -> None:
    op.drop_index('ix_sync_logs_connection_id', table_name='sync_logs')
    op.drop_table('sync_logs')

    op.drop_unique_constraint('uq_email_routing_rules_user_email_match', 'email_routing_rules')
    op.drop_index('ix_email_routing_rules_client_id', table_name='email_routing_rules')
    op.drop_index('ix_email_routing_rules_email_address', table_name='email_routing_rules')
    op.drop_index('ix_email_routing_rules_user_id', table_name='email_routing_rules')
    op.drop_table('email_routing_rules')

    op.drop_unique_constraint('uq_integration_connections_user_provider_email', 'integration_connections')
    op.drop_index('ix_integration_connections_provider', table_name='integration_connections')
    op.drop_index('ix_integration_connections_user_id', table_name='integration_connections')
    op.drop_table('integration_connections')
