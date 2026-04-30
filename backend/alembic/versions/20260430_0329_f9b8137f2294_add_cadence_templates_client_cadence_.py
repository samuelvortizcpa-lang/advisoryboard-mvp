"""add cadence_templates, client_cadence schema and 4 preset seeds

Revision ID: f9b8137f2294
Revises: b59e25367fcc
Create Date: 2026-04-30 03:29:47.220776+00:00

Adds Layer 2 Gap 4 substrate:
- ENUM deliverable_key (7 values)
- cadence_templates (org-scoped + system, with is_system flag)
- cadence_template_deliverables (template <-> deliverable_key with is_enabled)
- client_cadence (one row per client, links to a template + JSONB overrides)
- organizations.default_cadence_template_id (additive column, FK)

Seeds 4 system presets (Full Cadence, Quarterly Only, Light Touch, Empty)
with all 28 (4 * 7) deliverable rows pre-populated. Disabled rows are
seeded explicitly so the toggle UI never has to insert-on-toggle.

Stamps existing orgs with 'Full Cadence' as their default so day-1
state is non-NULL for everyone. New orgs get the default via
client_service / org-create path (G4-P3).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic
revision: str = 'f9b8137f2294'
down_revision: Union[str, None] = 'b59e25367fcc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. ENUM type
    op.execute(
        "CREATE TYPE deliverable_key AS ENUM ("
        "'kickoff_memo', 'progress_note', 'quarterly_memo', "
        "'mid_year_tune_up', 'year_end_recap', 'pre_prep_brief', "
        "'post_prep_flag')"
    )

    # 2. cadence_templates
    op.create_table(
        "cadence_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(is_system = true AND org_id IS NULL) "
            "OR (is_system = false AND org_id IS NOT NULL)",
            name="cadence_templates_system_or_org",
        ),
    )
    op.create_index(
        "idx_cadence_templates_unique_active_name",
        "cadence_templates",
        ["org_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "idx_cadence_templates_org_active",
        "cadence_templates",
        ["org_id"],
        postgresql_where=sa.text("is_active = true"),
    )

    # 3. cadence_template_deliverables
    op.create_table(
        "cadence_template_deliverables",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cadence_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deliverable_key",
            postgresql.ENUM(
                "kickoff_memo",
                "progress_note",
                "quarterly_memo",
                "mid_year_tune_up",
                "year_end_recap",
                "pre_prep_brief",
                "post_prep_flag",
                name="deliverable_key",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.UniqueConstraint(
            "template_id",
            "deliverable_key",
            name="uq_template_deliverable",
        ),
    )

    # 4. client_cadence
    op.create_table(
        "client_cadence",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cadence_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "overrides",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("assigned_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_client_cadence_template",
        "client_cadence",
        ["template_id"],
    )

    # 5. organizations.default_cadence_template_id (additive column)
    op.add_column(
        "organizations",
        sa.Column(
            "default_cadence_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "cadence_templates.id",
                ondelete="SET NULL",
                name="fk_organizations_default_cadence_template",
            ),
            nullable=True,
        ),
    )

    # 6. Seed 4 system presets
    op.execute(
        """
        INSERT INTO cadence_templates (name, description, is_system, org_id)
        VALUES
            (
                'Full Cadence',
                'All advisory touchpoints — kickoff memo, 60-day progress note, quarterly memos, mid-year tune-up, year-end recap, plus tax-prep handoffs.',
                true,
                NULL
            ),
            (
                'Quarterly Only',
                'Quarterly written memos plus the year-end recap.',
                true,
                NULL
            ),
            (
                'Light Touch',
                'Year-end recap only.',
                true,
                NULL
            ),
            (
                'Empty',
                'Empty preset — pick deliverables one by one, or fork into a named firm preset.',
                true,
                NULL
            )
        """
    )

    # 7. Seed all 28 (4 templates * 7 deliverables) rows.
    # Disabled rows are seeded explicitly so toggles render in the UI
    # without insert-on-toggle.
    op.execute(
        """
        INSERT INTO cadence_template_deliverables (template_id, deliverable_key, is_enabled)
        SELECT t.id, k.deliverable_key::deliverable_key, k.is_enabled
        FROM cadence_templates t
        JOIN (VALUES
            -- Full Cadence: all 7 enabled
            ('Full Cadence',  'kickoff_memo',     true),
            ('Full Cadence',  'progress_note',    true),
            ('Full Cadence',  'quarterly_memo',   true),
            ('Full Cadence',  'mid_year_tune_up', true),
            ('Full Cadence',  'year_end_recap',   true),
            ('Full Cadence',  'pre_prep_brief',   true),
            ('Full Cadence',  'post_prep_flag',   true),
            -- Quarterly Only: 2 enabled, 5 disabled
            ('Quarterly Only', 'kickoff_memo',     false),
            ('Quarterly Only', 'progress_note',    false),
            ('Quarterly Only', 'quarterly_memo',   true),
            ('Quarterly Only', 'mid_year_tune_up', false),
            ('Quarterly Only', 'year_end_recap',   true),
            ('Quarterly Only', 'pre_prep_brief',   false),
            ('Quarterly Only', 'post_prep_flag',   false),
            -- Light Touch: 1 enabled, 6 disabled
            ('Light Touch',   'kickoff_memo',     false),
            ('Light Touch',   'progress_note',    false),
            ('Light Touch',   'quarterly_memo',   false),
            ('Light Touch',   'mid_year_tune_up', false),
            ('Light Touch',   'year_end_recap',   true),
            ('Light Touch',   'pre_prep_brief',   false),
            ('Light Touch',   'post_prep_flag',   false),
            -- Empty: all 7 disabled
            ('Empty',         'kickoff_memo',     false),
            ('Empty',         'progress_note',    false),
            ('Empty',         'quarterly_memo',   false),
            ('Empty',         'mid_year_tune_up', false),
            ('Empty',         'year_end_recap',   false),
            ('Empty',         'pre_prep_brief',   false),
            ('Empty',         'post_prep_flag',   false)
        ) AS k(template_name, deliverable_key, is_enabled)
        ON t.name = k.template_name
        WHERE t.is_system = true
        """
    )

    # 8. Stamp existing orgs with 'Full Cadence' as default.
    op.execute(
        """
        UPDATE organizations
        SET default_cadence_template_id = (
            SELECT id FROM cadence_templates
            WHERE is_system = true AND name = 'Full Cadence'
        )
        WHERE default_cadence_template_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_organizations_default_cadence_template",
        "organizations",
        type_="foreignkey",
    )
    op.drop_column("organizations", "default_cadence_template_id")
    op.drop_index("idx_client_cadence_template", table_name="client_cadence")
    op.drop_table("client_cadence")
    op.drop_table("cadence_template_deliverables")
    op.drop_index(
        "idx_cadence_templates_org_active", table_name="cadence_templates"
    )
    op.drop_index(
        "idx_cadence_templates_unique_active_name",
        table_name="cadence_templates",
    )
    op.drop_table("cadence_templates")
    op.execute("DROP TYPE deliverable_key")
