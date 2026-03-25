"""Add tax strategy matrix: client profile flags, strategies table, status table with seed data.

Revision ID: d7e8f9a0b1c2
Revises: c5d9e3f7a8b4
Create Date: 2026-03-25
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

import uuid

# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c5d9e3f7a8b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add profile flag columns to clients ────────────────────────────
    for col in [
        "has_business_entity",
        "has_real_estate",
        "is_real_estate_professional",
        "has_high_income",
        "has_estate_planning",
        "is_medical_professional",
        "has_retirement_plans",
        "has_investments",
        "has_employees",
    ]:
        op.add_column(
            "clients",
            sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    # ── 2. Create tax_strategies table ────────────────────────────────────
    op.create_table(
        "tax_strategies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_flags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    # ── 3. Create client_strategy_status table ────────────────────────────
    op.create_table(
        "client_strategy_status",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "client_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tax_strategies.id"),
            nullable=False,
        ),
        sa.Column("tax_year", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'not_reviewed'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("estimated_impact", sa.Numeric(12, 2), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "strategy_id", "tax_year", name="uq_client_strategy_year"),
    )
    op.create_index("ix_client_strategy_status_client_id", "client_strategy_status", ["client_id"])
    op.create_index("ix_client_strategy_status_strategy_id", "client_strategy_status", ["strategy_id"])

    # ── 4. Seed tax_strategies ────────────────────────────────────────────
    strategies_table = sa.table(
        "tax_strategies",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
        sa.column("required_flags", JSONB),
        sa.column("display_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )

    rows = []

    # UNIVERSAL
    universal = [
        ("Roth IRA / Roth Conversion", "Direct contributions or conversion of traditional IRA/401k to Roth"),
        ("HSA Maximization", "Max contributions to Health Savings Account if HDHP eligible"),
        ("Charitable Giving Strategy", "Bunching, donor-advised funds, QCDs for 70.5+ taxpayers"),
        ("Tax-Loss Harvesting", "Offset capital gains with realized losses in investment portfolio"),
        ("529 Plan Contributions", "State tax deduction for education savings contributions"),
        ("Estimated Tax Optimization", "Quarterly payment timing to avoid penalties and optimize cash flow"),
        ("Filing Status Optimization", "MFJ vs MFS analysis, Head of Household qualification"),
        ("Withholding Review", "Annual W-4 review to avoid large refunds or underpayment"),
        ("Itemized vs Standard Deduction", "Annual analysis of deduction method, bunching strategy"),
    ]
    for i, (name, desc) in enumerate(universal, 1):
        rows.append({"id": uuid.uuid4(), "name": name, "category": "universal", "description": desc, "required_flags": [], "display_order": i, "is_active": True})

    # BUSINESS
    business = [
        ("Augusta Rule (Section 280A)", "Rent personal residence to business for up to 14 days tax-free"),
        ("Section 199A (QBI Deduction)", "Qualified Business Income deduction for pass-through entities"),
        ("Reasonable Compensation Analysis", "S-Corp officer salary optimization to minimize SE tax"),
        ("Entity Structure Review", "Annual review of entity type (LLC, S-Corp, C-Corp) for tax efficiency"),
        ("Accountable Plan", "Employee expense reimbursement plan for tax-free business deductions"),
        ("Home Office Deduction", "Simplified or actual method for dedicated home office space"),
        ("Vehicle Deduction Strategy", "Actual expenses vs standard mileage, Section 179 for business vehicles"),
        ("SEP-IRA / Solo 401(k)", "Retirement plan contributions for self-employed or small business owners"),
        ("Section 179 / Bonus Depreciation", "Accelerated depreciation on business equipment and assets"),
        ("R&D Tax Credit", "Credit for qualified research activities and expenses"),
        ("Hiring Incentive Credits", "Work Opportunity Tax Credit and similar employment-based credits"),
        ("Cash Balance / Defined Benefit Plan", "High-deduction retirement plan for high-income business owners"),
    ]
    for i, (name, desc) in enumerate(business, 1):
        rows.append({"id": uuid.uuid4(), "name": name, "category": "business", "description": desc, "required_flags": ["has_business_entity"], "display_order": i, "is_active": True})

    # REAL_ESTATE
    real_estate = [
        ("Cost Segregation Study", "Accelerate depreciation on commercial/rental property components"),
        ("1031 Exchange", "Defer capital gains on sale of investment property by reinvesting"),
        ("RE Professional Status", "Qualify to deduct rental losses against ordinary income (750+ hrs)"),
        ("Short-Term Rental Loophole", "Material participation in STR to offset W-2 income with depreciation"),
        ("Passive Activity Review", "Annual review of passive losses, grouping elections, and at-risk rules"),
        ("Opportunity Zone Investment", "Defer and reduce capital gains through Qualified Opportunity Zone funds"),
        ("MACRS Depreciation Review", "Ensure correct useful lives and methods for all property assets"),
    ]
    for i, (name, desc) in enumerate(real_estate, 1):
        rows.append({"id": uuid.uuid4(), "name": name, "category": "real_estate", "description": desc, "required_flags": ["has_real_estate"], "display_order": i, "is_active": True})

    # HIGH_INCOME
    high_income = [
        ("Backdoor Roth IRA", "Non-deductible traditional IRA contribution + Roth conversion"),
        ("Mega Backdoor Roth", "After-tax 401(k) contributions with in-plan Roth conversion"),
        ("Net Investment Income Tax Planning", "Strategies to minimize 3.8% NIIT on investment income"),
        ("Income Timing / Deferral", "Accelerate deductions or defer income across tax years"),
    ]
    for i, (name, desc) in enumerate(high_income, 1):
        rows.append({"id": uuid.uuid4(), "name": name, "category": "high_income", "description": desc, "required_flags": ["has_high_income"], "display_order": i, "is_active": True})

    # ESTATE
    estate = [
        ("Irrevocable Life Insurance Trust", "ILIT to remove life insurance from taxable estate"),
        ("Grantor Retained Annuity Trust", "GRAT for transferring appreciating assets at reduced gift tax"),
        ("Annual Gift Exclusion", "Systematic use of annual exclusion to reduce estate"),
        ("Charitable Remainder Trust", "CRT for income stream with charitable remainder"),
        ("Captive Insurance", "Small captive insurance company for risk management and deductions"),
    ]
    for i, (name, desc) in enumerate(estate, 1):
        rows.append({"id": uuid.uuid4(), "name": name, "category": "estate", "description": desc, "required_flags": ["has_estate_planning"], "display_order": i, "is_active": True})

    # MEDICAL
    medical = [
        ("Student Loan Strategies", "PSLF, refinancing analysis, employer repayment programs"),
        ("Disability Insurance Review", "Own-occupation coverage, tax treatment of premiums vs benefits"),
        ("Practice Entity Optimization", "PA/PLLC structure, management company split, compensation planning"),
    ]
    for i, (name, desc) in enumerate(medical, 1):
        rows.append({"id": uuid.uuid4(), "name": name, "category": "medical", "description": desc, "required_flags": ["is_medical_professional"], "display_order": i, "is_active": True})

    op.bulk_insert(strategies_table, rows)


def downgrade() -> None:
    op.drop_table("client_strategy_status")
    op.drop_table("tax_strategies")

    for col in [
        "has_business_entity",
        "has_real_estate",
        "is_real_estate_professional",
        "has_high_income",
        "has_estate_planning",
        "is_medical_professional",
        "has_retirement_plans",
        "has_investments",
        "has_employees",
    ]:
        op.drop_column("clients", col)
