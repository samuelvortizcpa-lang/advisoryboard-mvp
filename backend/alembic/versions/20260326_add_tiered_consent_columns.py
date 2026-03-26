"""Add preparer flag and data handling acknowledgment for tiered 7216 consent.

Adds is_tax_preparer, data_handling_acknowledged, data_handling_acknowledged_at
to clients table. Adds consent_tier to client_consents table.
Updates consent_status allowed values to include 'acknowledged'.

Revision ID: e9f0a1b2c3d4
Revises: d7e8f9a0b1c2
Create Date: 2026-03-26
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add tiered consent columns to clients ─────────────────────────
    op.add_column(
        "clients",
        sa.Column("is_tax_preparer", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column(
            "data_handling_acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "clients",
        sa.Column(
            "data_handling_acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ── 2. Add consent_tier to client_consents ───────────────────────────
    op.add_column(
        "client_consents",
        sa.Column(
            "consent_tier",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'full_7216'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("client_consents", "consent_tier")
    op.drop_column("clients", "data_handling_acknowledged_at")
    op.drop_column("clients", "data_handling_acknowledged")
    op.drop_column("clients", "is_tax_preparer")
