"""add client_kind and client_links table

Revision ID: bcbd1890f4df
Revises: 14ae485b1dec
Create Date: 2026-04-17 00:17:59.093546+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic
revision: str = 'bcbd1890f4df'
down_revision: Union[str, None] = '14ae485b1dec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add client_kind column to clients
    op.add_column(
        'clients',
        sa.Column(
            'client_kind',
            sa.Text(),
            nullable=False,
            server_default='unknown',
        ),
    )

    # Add CHECK constraint for valid client_kind values
    op.create_check_constraint(
        'ck_clients_client_kind',
        'clients',
        "client_kind IN ('individual', 's_corp', 'partnership', 'c_corp', "
        "'trust', 'disregarded_llc', 'sole_prop', 'unknown')",
    )

    # 2. Backfill: clients with any chunk mentioning "Form 1040" -> individual
    op.execute("""
        UPDATE clients
        SET client_kind = 'individual'
        WHERE id IN (
            SELECT DISTINCT dc.client_id
            FROM document_chunks dc
            WHERE dc.chunk_text ILIKE '%%form 1040%%'
        )
    """)

    # 3. Create client_links table
    op.create_table(
        'client_links',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('human_client_id', UUID(as_uuid=True), nullable=False),
        sa.Column('entity_client_id', UUID(as_uuid=True), nullable=False),
        sa.Column('link_type', sa.Text(), nullable=False),
        sa.Column('ownership_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('filing_responsibility', sa.Text(), nullable=False),
        sa.Column('confirmed_by_user', sa.Boolean(), nullable=False, server_default=sa.text('FALSE')),
        sa.Column('detection_source', sa.Text(), nullable=True),
        sa.Column('detection_confidence', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['human_client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('human_client_id', 'entity_client_id'),
    )

    # 4. Partial indexes for confirmed links
    op.create_index(
        'idx_client_links_human',
        'client_links',
        ['human_client_id'],
        postgresql_where=sa.text('confirmed_by_user = TRUE'),
    )
    op.create_index(
        'idx_client_links_entity',
        'client_links',
        ['entity_client_id'],
        postgresql_where=sa.text('confirmed_by_user = TRUE'),
    )

    # CHECK constraints for link_type and filing_responsibility
    op.create_check_constraint(
        'ck_client_links_link_type',
        'client_links',
        "link_type IN ('owner_of', 'partner_in', 'beneficiary_of', 'officer_of')",
    )
    op.create_check_constraint(
        'ck_client_links_filing_responsibility',
        'client_links',
        "filing_responsibility IN ('firm_files', 'k1_only', 'external_cpa', 'advised_only', 'unknown')",
    )

    # 5. Trigger to enforce human→entity invariant
    op.execute("""
        CREATE OR REPLACE FUNCTION check_client_link_kinds()
        RETURNS TRIGGER AS $$
        DECLARE
            human_kind TEXT;
            entity_kind TEXT;
        BEGIN
            SELECT client_kind INTO human_kind
            FROM clients WHERE id = NEW.human_client_id;

            SELECT client_kind INTO entity_kind
            FROM clients WHERE id = NEW.entity_client_id;

            IF human_kind IS NULL THEN
                RAISE EXCEPTION 'human_client_id does not reference an existing client';
            END IF;

            IF entity_kind IS NULL THEN
                RAISE EXCEPTION 'entity_client_id does not reference an existing client';
            END IF;

            IF human_kind != 'individual' THEN
                RAISE EXCEPTION 'human_client_id must reference a client with client_kind=individual (got %)', human_kind;
            END IF;

            IF entity_kind NOT IN ('s_corp', 'partnership', 'c_corp', 'trust', 'disregarded_llc', 'sole_prop') THEN
                RAISE EXCEPTION 'entity_client_id must reference a business/trust client_kind (got %)', entity_kind;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_check_client_link_kinds
        BEFORE INSERT OR UPDATE ON client_links
        FOR EACH ROW EXECUTE FUNCTION check_client_link_kinds();
    """)


def downgrade() -> None:
    # Drop trigger and function first (depend on the table)
    op.execute("DROP TRIGGER IF EXISTS trg_check_client_link_kinds ON client_links")
    op.execute("DROP FUNCTION IF EXISTS check_client_link_kinds()")

    # Drop indexes
    op.drop_index('idx_client_links_entity', table_name='client_links')
    op.drop_index('idx_client_links_human', table_name='client_links')

    # Drop client_links table
    op.drop_table('client_links')

    # Drop client_kind CHECK constraint and column
    op.drop_constraint('ck_clients_client_kind', 'clients', type_='check')
    op.drop_column('clients', 'client_kind')
