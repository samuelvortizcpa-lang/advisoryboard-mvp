"""Per-form line-group section definitions for form_aware_chunker v2.

Each form's sections are defined as a list of dicts with:
- `lines`: list of line identifiers (strings, preserving form format like "1a", "5d")
- `section`: narrative section name matching spec §5 format
- `transfers_to`: optional annotation for schedule→parent-form bridges

The chunker uses these tables to detect section boundaries by matching
observed line numbers against the `lines` field of each entry.

Tier 1: Schedule A (Q7 root cause)
Tier 2: Form 1040 main + Schedules B/D/1/2/3 + Forms 8889/5329/8283/4562/8960/8995

Spec reference: AdvisoryBoard_FormAware_Chunker_Spec.md §4-5
"""

from __future__ import annotations
from typing import Optional, TypedDict


class SectionEntry(TypedDict):
    lines: list[str]
    section: str
    transfers_to: Optional[str]


# ============================================================================
# TIER 1: Schedule A (Form 1040) — Itemized Deductions
# Fixes Q7 (charity citation) — ROOT CAUSE SECTION
# ============================================================================

SCHEDULE_A_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4"],
        "section": "Medical and Dental Expenses - Lines 1-4 (transfers to Form 1040 Line 12)",
        "transfers_to": "Form 1040 Line 12",
    },
    {
        "lines": ["5", "5a", "5b", "5c", "5d", "5e", "6", "7"],
        "section": "Taxes You Paid - Lines 5-7 (transfers to Form 1040 Line 12)",
        "transfers_to": "Form 1040 Line 12",
    },
    {
        "lines": ["8", "8a", "8b", "8c", "8d", "8e", "9", "10"],
        "section": "Interest You Paid - Lines 8-10 (transfers to Form 1040 Line 12)",
        "transfers_to": "Form 1040 Line 12",
    },
    {
        "lines": ["11", "12", "13", "14"],
        "section": "Gifts to Charity - Lines 11-14 (transfers to Form 1040 Line 12)",
        "transfers_to": "Form 1040 Line 12",
    },
    {
        "lines": ["15"],
        "section": "Casualty and Theft Losses - Line 15",
        "transfers_to": None,
    },
    {
        "lines": ["16"],
        "section": "Other Itemized Deductions - Line 16",
        "transfers_to": None,
    },
    {
        "lines": ["17"],
        "section": "Total Itemized Deductions - Line 17 (transfers to Form 1040 Line 12)",
        "transfers_to": "Form 1040 Line 12",
    },
    {
        "lines": ["18"],
        "section": "Elect to Itemize When Less Than Standard - Line 18",
        "transfers_to": None,
    },
]


# ============================================================================
# TIER 2: Form 1040 main (pages 5-6) + Schedules B, D, 1, 2, 3
# Plus Forms 8889, 5329, 8283, 4562, 8960, 8995, 8995-A
# ============================================================================

FORM_1040_SECTIONS: list[SectionEntry] = [
    # Page 5 — top of return
    {
        "lines": ["1a", "1b", "1c", "1d", "1e", "1f", "1g", "1h", "1i", "1z"],
        "section": "Wages - Lines 1a-1z",
        "transfers_to": None,
    },
    {
        "lines": ["2a", "2b"],
        "section": "Interest - Lines 2a-2b (tax-exempt and taxable; 2b transfers from Schedule B Part I)",
        "transfers_to": None,
    },
    {
        "lines": ["3a", "3b"],
        "section": "Dividends - Lines 3a-3b (qualified and ordinary; 3b transfers from Schedule B Part II)",
        "transfers_to": None,
    },
    {
        "lines": ["4a", "4b"],
        "section": "IRA Distributions - Lines 4a-4b",
        "transfers_to": None,
    },
    {
        "lines": ["5a", "5b"],
        "section": "Pensions and Annuities - Lines 5a-5b",
        "transfers_to": None,
    },
    {
        "lines": ["6a", "6b", "6c"],
        "section": "Social Security Benefits - Lines 6a-6c",
        "transfers_to": None,
    },
    {
        "lines": ["7"],
        "section": "Capital Gain or Loss - Line 7 (transfers from Schedule D Line 16)",
        "transfers_to": None,
    },
    {
        "lines": ["8"],
        "section": "Additional Income - Line 8 (transfers from Schedule 1 Line 10)",
        "transfers_to": None,
    },
    {
        "lines": ["9"],
        "section": "Total Income - Line 9",
        "transfers_to": None,
    },
    {
        "lines": ["10"],
        "section": "Adjustments to Income - Line 10 (transfers from Schedule 1 Line 26)",
        "transfers_to": None,
    },
    {
        "lines": ["11"],
        "section": "Adjusted Gross Income - Line 11",
        "transfers_to": None,
    },
    {
        "lines": ["12"],
        "section": "Standard Deduction or Itemized Deductions - Line 12 (transfers from Schedule A Line 17 if itemizing)",
        "transfers_to": None,
    },
    {
        "lines": ["13"],
        "section": "Qualified Business Income Deduction - Line 13 (transfers from Form 8995 or 8995-A)",
        "transfers_to": None,
    },
    {
        "lines": ["14", "15"],
        "section": "Taxable Income - Lines 14-15",
        "transfers_to": None,
    },
    # Page 6 — bottom of return
    {
        "lines": ["16"],
        "section": "Tax - Line 16",
        "transfers_to": None,
    },
    {
        "lines": ["17", "18"],
        "section": "Additional Taxes and Credits - Lines 17-18",
        "transfers_to": None,
    },
    {
        "lines": ["19"],
        "section": "Child Tax Credit - Line 19",
        "transfers_to": None,
    },
    {
        "lines": ["20"],
        "section": "Other Credits - Line 20 (transfers from Schedule 3 Line 8)",
        "transfers_to": None,
    },
    {
        "lines": ["21", "22"],
        "section": "Subtotal Credits and Subtract - Lines 21-22",
        "transfers_to": None,
    },
    {
        "lines": ["23"],
        "section": "Other Taxes - Line 23 (transfers from Schedule 2 Line 21)",
        "transfers_to": None,
    },
    {
        "lines": ["24"],
        "section": "Total Tax - Line 24",
        "transfers_to": None,
    },
    {
        "lines": ["25", "25a", "25b", "25c"],
        "section": "Federal Income Tax Withheld - Lines 25a-25c",
        "transfers_to": None,
    },
    {
        "lines": ["26"],
        "section": "Estimated Tax Payments - Line 26",
        "transfers_to": None,
    },
    {
        "lines": ["27"],
        "section": "Earned Income Credit - Line 27",
        "transfers_to": None,
    },
    {
        "lines": ["28"],
        "section": "Additional Child Tax Credit - Line 28",
        "transfers_to": None,
    },
    {
        "lines": ["29"],
        "section": "American Opportunity Credit - Line 29",
        "transfers_to": None,
    },
    {
        "lines": ["30", "31"],
        "section": "Other Payments and Refundable Credits - Lines 30-31 (transfers from Schedule 3 Line 15)",
        "transfers_to": None,
    },
    {
        "lines": ["32", "33"],
        "section": "Total Payments - Lines 32-33",
        "transfers_to": None,
    },
    {
        "lines": ["34", "35a", "35b", "35c", "35d", "36"],
        "section": "Refund - Lines 34-36",
        "transfers_to": None,
    },
    {
        "lines": ["37", "38"],
        "section": "Amount You Owe - Lines 37-38",
        "transfers_to": None,
    },
]


SCHEDULE_B_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4"],
        "section": "Part I Interest - Lines 1-4 (transfers to Form 1040 Line 2b)",
        "transfers_to": "Form 1040 Line 2b",
    },
    {
        "lines": ["5", "6"],
        "section": "Part II Ordinary Dividends - Lines 5-6 (transfers to Form 1040 Line 3b)",
        "transfers_to": "Form 1040 Line 3b",
    },
    {
        "lines": ["7", "7a", "7b", "8"],
        "section": "Part III Foreign Accounts and Trusts - Lines 7a-8",
        "transfers_to": None,
    },
]


SCHEDULE_D_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1a", "1b", "2", "3", "4", "5", "6", "7"],
        "section": "Part I Short-Term Capital Gains and Losses - Lines 1a-7",
        "transfers_to": None,
    },
    {
        "lines": ["8a", "8b", "9", "10", "11", "12", "13", "14", "15"],
        "section": "Part II Long-Term Capital Gains and Losses - Lines 8a-15",
        "transfers_to": None,
    },
    {
        "lines": ["16", "17", "18", "19", "20", "21", "22"],
        "section": "Part III Summary - Lines 16-22 (Line 16 transfers to Form 1040 Line 7)",
        "transfers_to": "Form 1040 Line 7",
    },
]


SCHEDULE_1_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2a", "2b", "3", "4", "5", "6", "7", "8", "8a", "8b", "8c", "8d", "8e", "8f", "8g", "8h", "8i", "8j", "8k", "8l", "8m", "8n", "8o", "8p", "8q", "8r", "8s", "8t", "8u", "8v", "8z", "9", "10"],
        "section": "Part I Additional Income - Lines 1-10 (transfers to Form 1040 Line 8)",
        "transfers_to": "Form 1040 Line 8",
    },
    {
        "lines": ["11", "12", "13", "14", "15", "16", "17", "18", "19a", "19b", "19c", "20", "21", "22", "23", "24", "24a", "24b", "24c", "24d", "24e", "24f", "24g", "24h", "24i", "24j", "24k", "24z", "25", "26"],
        "section": "Part II Adjustments to Income - Lines 11-26 (transfers to Form 1040 Line 10)",
        "transfers_to": "Form 1040 Line 10",
    },
]


SCHEDULE_2_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3"],
        "section": "Part I Tax - Lines 1-3 (transfers to Form 1040 Line 17)",
        "transfers_to": "Form 1040 Line 17",
    },
    {
        "lines": ["4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "17a", "17b", "17c", "17d", "17e", "17f", "17g", "17h", "17i", "17j", "17k", "17l", "17m", "17n", "17o", "17p", "17q", "17z", "18", "19", "20", "21"],
        "section": "Part II Other Taxes - Lines 4-21 (transfers to Form 1040 Line 23)",
        "transfers_to": "Form 1040 Line 23",
    },
]


SCHEDULE_3_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5a", "5b", "6", "6a", "6b", "6c", "6d", "6e", "6f", "6g", "6h", "6i", "6j", "6k", "6l", "6m", "6z", "7", "8"],
        "section": "Part I Nonrefundable Credits - Lines 1-8 (transfers to Form 1040 Line 20)",
        "transfers_to": "Form 1040 Line 20",
    },
    {
        "lines": ["9", "10", "11", "12", "13", "13a", "13b", "13c", "13d", "13z", "14", "15"],
        "section": "Part II Other Payments and Refundable Credits - Lines 9-15 (transfers to Form 1040 Line 31)",
        "transfers_to": "Form 1040 Line 31",
    },
]


FORM_8889_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"],
        "section": "Part I HSA Contributions - Lines 1-13 (Line 13 transfers to Schedule 1 Line 13)",
        "transfers_to": "Schedule 1 Line 13",
    },
    {
        "lines": ["14a", "14b", "14c", "15", "16", "17", "17a", "17b"],
        "section": "Part II HSA Distributions - Lines 14a-17b",
        "transfers_to": None,
    },
    {
        "lines": ["18", "19", "20", "21"],
        "section": "Part III Income and Additional Tax for Failure to Maintain HDHP Coverage - Lines 18-21",
        "transfers_to": None,
    },
]


FORM_5329_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4"],
        "section": "Part I Additional Tax on Early Distributions - Lines 1-4",
        "transfers_to": None,
    },
    {
        "lines": ["5", "6", "7", "8"],
        "section": "Part II Additional Tax on Certain Distributions from Education Accounts - Lines 5-8",
        "transfers_to": None,
    },
    {
        "lines": ["9", "10", "11", "12", "13", "14", "15", "16", "17"],
        "section": "Part III Additional Tax on Excess Contributions to Traditional IRAs - Lines 9-17",
        "transfers_to": None,
    },
    {
        "lines": ["18", "19", "20", "21", "22", "23", "24", "25"],
        "section": "Part IV Additional Tax on Excess Contributions to Roth IRAs - Lines 18-25 (transfers to Schedule 2 Line 8)",
        "transfers_to": "Schedule 2 Line 8",
    },
    {
        "lines": ["26", "27", "28", "29", "30", "31", "32", "33"],
        "section": "Part V Additional Tax on Excess Contributions to Coverdell ESAs - Lines 26-33",
        "transfers_to": None,
    },
    {
        "lines": ["34", "35", "36", "37", "38", "39", "40", "41"],
        "section": "Part VI Additional Tax on Excess Contributions to Archer MSAs - Lines 34-41",
        "transfers_to": None,
    },
    {
        "lines": ["42", "43", "44", "45", "46", "47", "48", "49"],
        "section": "Part VII Additional Tax on Excess Contributions to HSAs - Lines 42-49",
        "transfers_to": None,
    },
    {
        "lines": ["50", "51", "52", "53"],
        "section": "Part VIII Additional Tax on Excess Contributions to ABLE Account - Lines 50-53",
        "transfers_to": None,
    },
    {
        "lines": ["54", "55"],
        "section": "Part IX Additional Tax on Excess Accumulation in Qualified Retirement Plans - Lines 54-55",
        "transfers_to": None,
    },
]


FORM_8283_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5"],
        "section": "Section A - Donated Property of $5,000 or Less and Publicly Traded Securities",
        "transfers_to": None,
    },
    {
        "lines": ["6", "7", "8", "9", "10", "11", "12"],
        "section": "Section B - Donated Property Over $5,000 Except Publicly Traded Securities",
        "transfers_to": None,
    },
]


FORM_4562_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"],
        "section": "Part I Election To Expense Certain Property Under Section 179 - Lines 1-13",
        "transfers_to": None,
    },
    {
        "lines": ["14", "15", "16"],
        "section": "Part II Special Depreciation Allowance and Other Depreciation - Lines 14-16",
        "transfers_to": None,
    },
    {
        "lines": ["17", "18", "19a", "19b", "19c", "19d", "19e", "19f", "19g", "19h", "19i", "20a", "20b", "20c", "20d", "21"],
        "section": "Part III MACRS Depreciation - Lines 17-21",
        "transfers_to": None,
    },
    {
        "lines": ["22", "23"],
        "section": "Part IV Summary - Lines 22-23",
        "transfers_to": None,
    },
    {
        "lines": ["24a", "24b", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36"],
        "section": "Part V Listed Property - Lines 24-36",
        "transfers_to": None,
    },
    {
        "lines": ["37", "38", "39", "40", "41", "42", "43", "44"],
        "section": "Part VI Amortization - Lines 37-44",
        "transfers_to": None,
    },
]


FORM_8960_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4a", "4b", "4c", "5a", "5b", "5c", "5d", "6", "7", "8"],
        "section": "Part I Investment Income - Lines 1-8",
        "transfers_to": None,
    },
    {
        "lines": ["9a", "9b", "9c", "10", "11"],
        "section": "Part II Investment Expenses Allocable to Investment Income - Lines 9-11",
        "transfers_to": None,
    },
    {
        "lines": ["12", "13", "14", "15", "16", "17"],
        "section": "Part III Tax Computation for Individuals - Lines 12-17",
        "transfers_to": None,
    },
    {
        "lines": ["18a", "18b", "18c", "19a", "19b", "19c", "20", "21"],
        "section": "Part III Tax Computation for Estates and Trusts - Lines 18-21",
        "transfers_to": None,
    },
]


FORM_8995_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "1a", "1b", "1c", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17"],
        "section": "Form 8995 Simplified QBI Deduction Computation - Lines 1-17",
        "transfers_to": "Form 1040 Line 13",
    },
]


FORM_8995_A_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5"],
        "section": "Part I Trade, Business, or Aggregation Information - Lines 1-5",
        "transfers_to": None,
    },
    {
        "lines": ["6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"],
        "section": "Part II Determine Your Adjusted QBI - Lines 6-16",
        "transfers_to": None,
    },
    {
        "lines": ["17", "18", "19", "20", "21", "22", "23", "24", "25", "26"],
        "section": "Part III Phased-in Reduction - Lines 17-26",
        "transfers_to": None,
    },
    {
        "lines": ["27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39"],
        "section": "Part IV Determine Your QBI Deduction - Lines 27-39 (Line 39 transfers to Form 1040 Line 13)",
        "transfers_to": "Form 1040 Line 13",
    },
]


# ============================================================================
# TIER 3: S-corp family (Form 1120S + Schedule K + K-1 + Form 7203)
# Plus Forms 8879-CORP, 1125-E, 1125-A, and S-corp supporting schedules
# ============================================================================

FORM_1120S_SECTIONS: list[SectionEntry] = [
    # Page 1 — Identifying info, Income, Deductions, Tax and Payments
    {
        "lines": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        "section": "Page 1 Header - Election Info, EIN, Address, Activity Codes",
        "transfers_to": None,
    },
    {
        "lines": ["1a", "1b", "1c", "2", "3", "4", "5", "6"],
        "section": "Income - Lines 1a-6 (Gross Receipts, COGS, Gross Profit, Other Income)",
        "transfers_to": None,
    },
    {
        "lines": ["7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20"],
        "section": "Deductions - Lines 7-20 (Compensation, Salaries, Repairs, Taxes, Depreciation, Other)",
        "transfers_to": None,
    },
    {
        "lines": ["21"],
        "section": "Ordinary Business Income (Loss) - Line 21 (transfers to Schedule K Line 1)",
        "transfers_to": "Schedule K Line 1",
    },
    {
        "lines": ["22a", "22b", "22c", "23a", "23b", "23c", "23d", "24", "25", "26", "27"],
        "section": "Tax and Payments - Lines 22-27 (Excess Net Passive Income Tax, Estimated Payments, Amount Owed/Refund)",
        "transfers_to": None,
    },
]


FORM_1120S_SCHEDULE_B_SECTIONS: list[SectionEntry] = [
    # Note: this is 1120S's internal Schedule B, different from Form 1040 Schedule B
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14"],
        "section": "Page 2 Schedule B Other Information - Lines 1-14",
        "transfers_to": None,
    },
]


SCHEDULE_K_1120S_SECTIONS: list[SectionEntry] = [
    # Schedule K on Form 1120S pages 3-4 — Shareholders' Pro Rata Share Items
    {
        "lines": ["1"],
        "section": "Schedule K Income (Loss) - Line 1 Ordinary Business Income from 1120S Line 21",
        "transfers_to": None,
    },
    {
        "lines": ["2", "3a", "3b", "3c"],
        "section": "Schedule K Rental Real Estate and Other Rental Income - Lines 2-3c",
        "transfers_to": None,
    },
    {
        "lines": ["4", "5a", "5b"],
        "section": "Schedule K Interest and Dividend Income - Lines 4-5b",
        "transfers_to": None,
    },
    {
        "lines": ["6", "7", "8a", "8b", "8c", "9", "10"],
        "section": "Schedule K Royalty, Capital Gain, and Other Income - Lines 6-10",
        "transfers_to": None,
    },
    {
        "lines": ["11", "12a", "12b", "12c", "12d"],
        "section": "Schedule K Deductions - Lines 11-12d (Section 179, Charitable, Investment Interest, Section 59e Expenses)",
        "transfers_to": None,
    },
    {
        "lines": ["13a", "13b", "13c", "13d", "13e", "13f", "13g", "13h"],
        "section": "Schedule K Credits - Lines 13a-13h",
        "transfers_to": None,
    },
    {
        "lines": ["14a", "14b", "14c", "14d", "14e", "14f", "14g", "14h", "14i", "14j", "14k", "14l", "14m", "14n", "14o", "14p", "14q", "14r", "14s"],
        "section": "Schedule K Foreign Transactions - Lines 14a-14s",
        "transfers_to": None,
    },
    {
        "lines": ["15a", "15b", "15c", "15d", "15e", "15f"],
        "section": "Schedule K Alternative Minimum Tax (AMT) Items - Lines 15a-15f",
        "transfers_to": None,
    },
    {
        "lines": ["16a", "16b", "16c", "16d", "16e", "16f"],
        "section": "Schedule K Items Affecting Shareholder Basis - Lines 16a-16f (Tax-Exempt Income, Nondeductible Expenses, Property Distributions)",
        "transfers_to": None,
    },
    {
        "lines": ["17a", "17b", "17c", "17d", "17e", "17f"],
        "section": "Schedule K Other Information - Lines 17a-17f",
        "transfers_to": None,
    },
    {
        "lines": ["18"],
        "section": "Schedule K Reconciliation - Line 18 Income (Loss) Reconciliation",
        "transfers_to": None,
    },
]


SCHEDULE_K1_1120S_SECTIONS: list[SectionEntry] = [
    # Schedule K-1 Form 1120S — Shareholder's Share of Income, Deductions, Credits
    # Different from Schedule K above — K is company-level, K-1 is per-shareholder
    {
        "lines": ["A", "B", "C", "D"],
        "section": "Part I Information About the Corporation - Items A-D (EIN, Name, IRS Center, S election date)",
        "transfers_to": None,
    },
    {
        "lines": ["E", "F", "G", "H", "I", "J"],
        "section": "Part II Information About the Shareholder - Items E-J (Shareholder ID, Name, Address, Stock Ownership %)",
        "transfers_to": None,
    },
    {
        "lines": ["1"],
        "section": "Part III Line 1 Ordinary Business Income (Loss) (transfers to Schedule E Part II)",
        "transfers_to": "Schedule E Part II",
    },
    {
        "lines": ["2"],
        "section": "Part III Line 2 Net Rental Real Estate Income (Loss)",
        "transfers_to": None,
    },
    {
        "lines": ["3"],
        "section": "Part III Line 3 Other Net Rental Income (Loss)",
        "transfers_to": None,
    },
    {
        "lines": ["4"],
        "section": "Part III Line 4 Interest Income (transfers to Schedule B Line 1)",
        "transfers_to": "Schedule B Line 1",
    },
    {
        "lines": ["5a", "5b"],
        "section": "Part III Lines 5a-5b Dividends (Ordinary and Qualified; transfers to Form 1040 Lines 3a, 3b)",
        "transfers_to": "Form 1040 Lines 3a, 3b",
    },
    {
        "lines": ["6"],
        "section": "Part III Line 6 Royalties (transfers to Schedule E Line 4)",
        "transfers_to": "Schedule E Line 4",
    },
    {
        "lines": ["7", "8a", "8b", "8c", "9"],
        "section": "Part III Lines 7-9 Capital Gains and Losses (transfers to Schedule D)",
        "transfers_to": "Schedule D",
    },
    {
        "lines": ["10"],
        "section": "Part III Line 10 Other Income (Loss)",
        "transfers_to": None,
    },
    {
        "lines": ["11"],
        "section": "Part III Line 11 Section 179 Deduction (transfers to Form 4562 Line 12)",
        "transfers_to": "Form 4562 Line 12",
    },
    {
        "lines": ["12"],
        "section": "Part III Line 12 Other Deductions (Charitable Contributions, Investment Interest, etc.)",
        "transfers_to": None,
    },
    {
        "lines": ["13"],
        "section": "Part III Line 13 Credits",
        "transfers_to": None,
    },
    {
        "lines": ["14"],
        "section": "Part III Line 14 Foreign Transactions",
        "transfers_to": None,
    },
    {
        "lines": ["15"],
        "section": "Part III Line 15 Alternative Minimum Tax (AMT) Items",
        "transfers_to": None,
    },
    {
        "lines": ["16"],
        "section": "Part III Line 16 Items Affecting Shareholder Basis (Tax-Exempt Income, Nondeductible Expenses, Distributions)",
        "transfers_to": None,
    },
    {
        "lines": ["17"],
        "section": "Part III Line 17 Other Information",
        "transfers_to": None,
    },
]


SCHEDULE_L_1120S_SECTIONS: list[SectionEntry] = [
    # Schedule L — Balance Sheets per Books (Form 1120S page 4)
    {
        "lines": ["1", "2a", "2b", "3", "4", "5", "6", "7a", "7b", "8", "9", "10a", "10b", "11", "12", "13", "14"],
        "section": "Schedule L Assets - Lines 1-14 (Cash, Receivables, Inventory, Investments, Buildings, Land, etc.)",
        "transfers_to": None,
    },
    {
        "lines": ["15"],
        "section": "Schedule L Total Assets - Line 15",
        "transfers_to": None,
    },
    {
        "lines": ["16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27"],
        "section": "Schedule L Liabilities and Shareholders' Equity - Lines 16-27",
        "transfers_to": None,
    },
]


SCHEDULE_M1_1120S_SECTIONS: list[SectionEntry] = [
    # Schedule M-1 — Reconciliation of Income per Books with Income per Return (Form 1120S page 5)
    {
        "lines": ["1", "2", "3", "4", "5a", "5b", "6", "7", "8"],
        "section": "Schedule M-1 Reconciliation of Income per Books with Income per Return - Lines 1-8",
        "transfers_to": None,
    },
]


SCHEDULE_M2_1120S_SECTIONS: list[SectionEntry] = [
    # Schedule M-2 — Analysis of AAA, OAA, PTI, ETI (Form 1120S page 5)
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8"],
        "section": "Schedule M-2 Analysis of AAA, OAA, PTI, ETI - Lines 1-8 (tracks accumulated earnings across periods)",
        "transfers_to": None,
    },
]


FORM_7203_SECTIONS: list[SectionEntry] = [
    # Shareholder Stock and Debt Basis Computation
    {
        "lines": ["1", "2", "3a", "3b", "3c", "3d", "3e", "3f", "3g", "3h", "3i", "3j", "3k"],
        "section": "Part I Shareholder Stock Basis - Lines 1-3k (Beginning Basis, Increases)",
        "transfers_to": None,
    },
    {
        "lines": ["4", "5a", "5b", "5c", "5d", "5e", "5f", "5g", "5h", "5i", "5j", "5k", "5l", "5m", "6", "7"],
        "section": "Part I Shareholder Stock Basis Continued - Lines 4-7 (Decreases, Distributions, Ending Basis)",
        "transfers_to": None,
    },
    {
        "lines": ["8", "9", "10", "11", "12a", "12b", "13", "14", "15"],
        "section": "Part II Shareholder Debt Basis - Lines 8-15",
        "transfers_to": None,
    },
    {
        "lines": ["16", "17a", "17b", "17c", "17d", "17e", "17f", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27"],
        "section": "Part III Shareholder Allowable Loss and Deduction Items - Lines 16-27",
        "transfers_to": None,
    },
]


FORM_8879_CORP_SECTIONS: list[SectionEntry] = [
    # E-file Signature Authorization for S-corp
    {
        "lines": ["1", "2", "3", "4", "5"],
        "section": "Form 8879-CORP E-file Signature Authorization - Lines 1-5 (single-section authorization)",
        "transfers_to": None,
    },
]


FORM_1125_E_SECTIONS: list[SectionEntry] = [
    # Compensation of Officers — attached to Form 1120S when gross receipts > $500K
    {
        "lines": ["1", "2", "3", "4"],
        "section": "Form 1125-E Compensation of Officers - Lines 1-4 (transfers to Form 1120S Line 7)",
        "transfers_to": "Form 1120S Line 7",
    },
]


FORM_1125_A_SECTIONS: list[SectionEntry] = [
    # Cost of Goods Sold — attached to Form 1120S/1120/1065 when applicable
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8"],
        "section": "Form 1125-A Cost of Goods Sold - Lines 1-8 (transfers to 1120S Line 2 or 1120 Line 2 or 1065 Line 2)",
        "transfers_to": "1120S/1120/1065 Line 2",
    },
    {
        "lines": ["9a", "9b", "9c", "9d", "9e", "9f"],
        "section": "Form 1125-A Additional Information - Lines 9a-9f",
        "transfers_to": None,
    },
]


# ============================================================================
# TIER 4: Partnerships (1065), Trusts (1041), Info Returns (W-2, 1099),
# Individual Schedules C/E/F/SE, State Returns
# ============================================================================

FORM_1065_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        "section": "Page 1 Header - Partnership Info, EIN, Activity Codes, Partner Count",
        "transfers_to": None,
    },
    {
        "lines": ["1a", "1b", "1c", "2", "3", "4", "5", "6", "7", "8"],
        "section": "Income - Lines 1a-8 (Gross Receipts, COGS, Gross Profit, Ordinary Income, Other Income)",
        "transfers_to": None,
    },
    {
        "lines": ["9", "10", "11", "12", "13", "14", "15", "16a", "16b", "16c", "17", "18", "19", "20", "21"],
        "section": "Deductions - Lines 9-21 (Salaries, Guaranteed Payments, Rent, Taxes, Depreciation, Other)",
        "transfers_to": None,
    },
    {
        "lines": ["22"],
        "section": "Ordinary Business Income (Loss) - Line 22 (transfers to Schedule K Line 1)",
        "transfers_to": "Schedule K Line 1",
    },
]


SCHEDULE_K_1065_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3a", "3b", "3c"],
        "section": "Schedule K Income (Loss) - Lines 1-3c (Ordinary Income, Rental, Other Rental)",
        "transfers_to": None,
    },
    {
        "lines": ["4", "5", "6a", "6b", "6c", "7", "8", "9a", "9b", "9c", "10", "11"],
        "section": "Schedule K Other Income - Lines 4-11 (Interest, Dividends, Royalties, Capital Gains, Section 1231, Other)",
        "transfers_to": None,
    },
    {
        "lines": ["12", "13a", "13b", "13c", "13d"],
        "section": "Schedule K Deductions - Lines 12-13d (Section 179, Charitable, Investment Interest)",
        "transfers_to": None,
    },
    {
        "lines": ["14a", "14b", "14c"],
        "section": "Schedule K Self-Employment - Lines 14a-14c (Net SE Earnings, Gross Farm/Non-farm Income)",
        "transfers_to": None,
    },
    {
        "lines": ["15a", "15b", "15c", "15d", "15e", "15f"],
        "section": "Schedule K Credits - Lines 15a-15f",
        "transfers_to": None,
    },
    {
        "lines": ["16a", "16b", "16c", "16d", "16e", "16f", "16g", "16h", "16i", "16j", "16k", "16l", "16m", "16n"],
        "section": "Schedule K Foreign Transactions - Lines 16a-16n",
        "transfers_to": None,
    },
    {
        "lines": ["17a", "17b", "17c", "17d", "17e", "17f"],
        "section": "Schedule K AMT Items - Lines 17a-17f",
        "transfers_to": None,
    },
    {
        "lines": ["18a", "18b", "18c", "19a", "19b", "20a", "20b", "20c"],
        "section": "Schedule K Tax-Exempt Income, Distributions, Other Info - Lines 18-20",
        "transfers_to": None,
    },
    {
        "lines": ["21"],
        "section": "Schedule K Analysis of Net Income (Loss) - Line 21",
        "transfers_to": None,
    },
]


SCHEDULE_K1_1065_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["A", "B", "C", "D"],
        "section": "Part I Information About the Partnership - Items A-D",
        "transfers_to": None,
    },
    {
        "lines": ["E", "F", "G", "H", "I1", "I2", "J", "K", "L", "M", "N"],
        "section": "Part II Information About the Partner - Items E-N (Partner ID, Profit/Loss/Capital %)",
        "transfers_to": None,
    },
    {
        "lines": ["1"],
        "section": "Part III Line 1 Ordinary Business Income (Loss) (transfers to Schedule E Part II)",
        "transfers_to": "Schedule E Part II",
    },
    {
        "lines": ["2", "3"],
        "section": "Part III Lines 2-3 Net Rental Real Estate and Other Rental Income (Loss)",
        "transfers_to": None,
    },
    {
        "lines": ["4a", "4b", "4c"],
        "section": "Part III Lines 4a-4c Guaranteed Payments (Services, Capital, Total)",
        "transfers_to": None,
    },
    {
        "lines": ["5", "6a", "6b", "6c", "7", "8", "9a", "9b", "9c", "10", "11"],
        "section": "Part III Lines 5-11 Interest, Dividends, Royalties, Capital Gains, Other Income",
        "transfers_to": None,
    },
    {
        "lines": ["12"],
        "section": "Part III Line 12 Section 179 Deduction",
        "transfers_to": "Form 4562 Line 12",
    },
    {
        "lines": ["13"],
        "section": "Part III Line 13 Other Deductions",
        "transfers_to": None,
    },
    {
        "lines": ["14"],
        "section": "Part III Line 14 Self-Employment Earnings (Loss)",
        "transfers_to": None,
    },
    {
        "lines": ["15", "16", "17", "18", "19", "20"],
        "section": "Part III Lines 15-20 Credits, Foreign Transactions, AMT, Tax-Exempt, Distributions, Other",
        "transfers_to": None,
    },
]


FORM_1041_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["A", "B", "C", "D", "E", "F", "G"],
        "section": "Header - Trust/Estate Info, Type of Entity, EIN",
        "transfers_to": None,
    },
    {
        "lines": ["1", "2a", "2b", "3", "4", "5", "6", "7", "8", "9"],
        "section": "Income - Lines 1-9 (Interest, Dividends, Business Income, Capital Gains, Rents, Farm, Other, Total)",
        "transfers_to": None,
    },
    {
        "lines": ["10", "11", "12", "13", "14", "15a", "15b", "16", "17"],
        "section": "Deductions - Lines 10-17 (Interest, Taxes, Fiduciary Fees, Charitable, Attorney/Accountant, Other, Total)",
        "transfers_to": None,
    },
    {
        "lines": ["18", "19", "20", "21", "22"],
        "section": "Tax Computation - Lines 18-22 (Adjusted Total Income, Income Distribution Deduction, Exemption, Taxable Income, Tax)",
        "transfers_to": None,
    },
    {
        "lines": ["23", "24a", "24b", "24c", "24d", "24e", "24f", "24g"],
        "section": "Taxes and Payments - Lines 23-24g (Total Tax, Estimated Payments, Withholding, Other Credits)",
        "transfers_to": None,
    },
    {
        "lines": ["25", "26", "27"],
        "section": "Refund or Amount Owed - Lines 25-27",
        "transfers_to": None,
    },
]


SCHEDULE_K1_1041_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["A", "B", "C", "D", "E"],
        "section": "Part I Information About the Estate or Trust - Items A-E (EIN, Name, Fiduciary)",
        "transfers_to": None,
    },
    {
        "lines": ["F", "G", "H", "I"],
        "section": "Part II Information About the Beneficiary - Items F-I (Beneficiary ID, Name, Type)",
        "transfers_to": None,
    },
    {
        "lines": ["1", "2a", "2b", "3", "4a", "4b", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14"],
        "section": "Part III Beneficiary's Share of Income, Deductions, Credits - Lines 1-14",
        "transfers_to": None,
    },
]


W2_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["a", "b", "c", "d", "e", "f"],
        "section": "Header - Control Number, EIN, Employer/Employee Name and Address",
        "transfers_to": None,
    },
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8"],
        "section": "Compensation - Lines 1-8 (Wages, Federal Tax Withheld, SS Wages/Tax, Medicare Wages/Tax, SS Tips, Allocated Tips)",
        "transfers_to": None,
    },
    {
        "lines": ["9", "10", "11", "12a", "12b", "12c", "12d", "13", "14"],
        "section": "Benefits and Other - Lines 9-14 (Verification Code, Dependent Care, Nonqualified Plans, Box 12 Codes, Statutory/Retirement/Sick Pay, Other)",
        "transfers_to": None,
    },
    {
        "lines": ["15", "16", "17", "18", "19", "20"],
        "section": "State/Local - Lines 15-20 (State, State Wages, State Tax, Local Wages, Local Tax, Locality Name)",
        "transfers_to": None,
    },
]


FORM_1099_INT_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17"],
        "section": "Form 1099-INT Interest Income - Lines 1-17 (Interest, Early Withdrawal Penalty, Federal Tax Withheld, Investment Expenses, Tax-Exempt Interest, State)",
        "transfers_to": None,
    },
]


FORM_1099_DIV_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1a", "1b", "2a", "2b", "2c", "2d", "2e", "2f", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"],
        "section": "Form 1099-DIV Dividends and Distributions - Lines 1a-16 (Ordinary, Qualified, Capital Gains, Nondividend, Section 199A, Foreign Tax, State)",
        "transfers_to": None,
    },
]


FORM_1099_B_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1a", "1b", "1c", "1d", "1e", "1f", "1g", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"],
        "section": "Form 1099-B Proceeds from Broker and Barter Exchange Transactions - Lines 1a-16",
        "transfers_to": None,
    },
]


FORM_1099_R_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2a", "2b", "3", "4", "5", "6", "7", "8", "9a", "9b", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19"],
        "section": "Form 1099-R Distributions From Pensions, Annuities, Retirement, IRAs - Lines 1-19",
        "transfers_to": None,
    },
]


FORM_1099_MISC_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18"],
        "section": "Form 1099-MISC Miscellaneous Information - Lines 1-18 (Rents, Royalties, Other Income, Medical, Nonemployee Comp, State)",
        "transfers_to": None,
    },
]


FORM_1099_NEC_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7"],
        "section": "Form 1099-NEC Nonemployee Compensation - Lines 1-7 (Nonemployee Compensation, Federal Tax Withheld, State)",
        "transfers_to": None,
    },
]


SSA_1099_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["3", "4", "5", "6", "7", "8", "9"],
        "section": "SSA-1099 Social Security Benefit Statement - Lines 3-9 (Benefits Paid, Repaid, Net Benefits, Voluntary Withholding)",
        "transfers_to": None,
    },
]


SCHEDULE_C_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        "section": "Header - Business Info, Accounting Method, Material Participation",
        "transfers_to": None,
    },
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7"],
        "section": "Part I Income - Lines 1-7 (Gross Receipts, Returns, COGS, Gross Profit, Other Income, Gross Income)",
        "transfers_to": None,
    },
    {
        "lines": ["8", "9", "10", "11", "12", "13", "14", "15", "16a", "16b", "17", "18", "19", "20a", "20b", "21", "22", "23", "24a", "24b", "25", "26", "27a", "27b", "28"],
        "section": "Part II Expenses - Lines 8-28 (Advertising, Car, Commissions, Depreciation, Insurance, Interest, Legal, Office, Rent, Wages, Other, Total)",
        "transfers_to": None,
    },
    {
        "lines": ["29", "30", "31"],
        "section": "Part II Net Profit or Loss - Lines 29-31 (transfers to Schedule 1 Line 3 or Schedule SE)",
        "transfers_to": "Schedule 1 Line 3",
    },
    {
        "lines": ["32", "33", "34", "35", "36", "37", "38", "39", "40", "41", "42"],
        "section": "Part III Cost of Goods Sold - Lines 33-42",
        "transfers_to": None,
    },
    {
        "lines": ["43", "44", "45", "46", "47", "48"],
        "section": "Part IV Information on Your Vehicle - Lines 43-48",
        "transfers_to": None,
    },
    {
        "lines": ["49", "50"],
        "section": "Part V Other Expenses - Lines 49-50",
        "transfers_to": None,
    },
]


SCHEDULE_E_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1a", "1b", "1c", "2"],
        "section": "Part I Rental/Royalty Property Info - Lines 1-2",
        "transfers_to": None,
    },
    {
        "lines": ["3a", "3b", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23a", "23b", "23c", "23d", "23e", "24", "25", "26"],
        "section": "Part I Rental/Royalty Income and Expenses - Lines 3-26 (Rents, Royalties, Expenses, Depreciation, Total, Net)",
        "transfers_to": None,
    },
    {
        "lines": ["27", "28", "29a", "29b", "30", "31", "32", "33a", "33b", "33c", "33d", "33e", "33f", "34a", "34b", "34c", "34d", "34e", "34f"],
        "section": "Part II Income or Loss From Partnerships and S Corporations - Lines 27-34 (K-1 income, Passive/Nonpassive, Totals)",
        "transfers_to": None,
    },
    {
        "lines": ["35", "36", "37", "38", "39", "40", "41", "42", "43"],
        "section": "Part III Income or Loss From Estates and Trusts - Lines 35-43",
        "transfers_to": None,
    },
    {
        "lines": ["44", "45", "46"],
        "section": "Part IV Income or Loss From REMICs - Lines 44-46",
        "transfers_to": None,
    },
    {
        "lines": ["47", "48"],
        "section": "Part V Summary - Lines 47-48 (Total and Farm Rental, transfers to Schedule 1 Line 5)",
        "transfers_to": "Schedule 1 Line 5",
    },
]


SCHEDULE_F_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["A", "B", "C", "D", "E", "F"],
        "section": "Header - Farm Info, Accounting Method, EIN",
        "transfers_to": None,
    },
    {
        "lines": ["1a", "1b", "1c", "2", "3a", "3b", "4a", "4b", "5a", "5b", "5c", "6a", "6b", "6d", "7", "8", "9"],
        "section": "Part I Farm Income Cash Method - Lines 1-9",
        "transfers_to": None,
    },
    {
        "lines": ["10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21a", "21b", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32a", "32b", "33", "34"],
        "section": "Part II Farm Expenses - Lines 10-34 (Car, Chemicals, Feed, Fertilizer, Insurance, Labor, Rent, Repairs, Seeds, Utilities, Vet, Other, Total)",
        "transfers_to": None,
    },
    {
        "lines": ["35", "36"],
        "section": "Part II Net Farm Profit (Loss) - Lines 35-36 (transfers to Schedule 1 Line 6)",
        "transfers_to": "Schedule 1 Line 6",
    },
]


SCHEDULE_SE_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1a", "1b", "2", "3", "4a", "4b", "4c", "5a", "5b", "6"],
        "section": "Section A Short Schedule SE - Lines 1a-6 (Net SE Earnings, SE Tax, Deduction)",
        "transfers_to": None,
    },
    {
        "lines": ["7", "8a", "8b", "9", "10", "11", "12", "13"],
        "section": "Section B Long Schedule SE - Lines 7-13 (Optional Method, SE Tax Computation, Deduction)",
        "transfers_to": None,
    },
]


# --- State returns (common ones) ---

FORM_D400_NC_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "10a", "10b", "11", "12a", "12b", "13", "14", "15", "16", "17", "18", "19", "20a", "20b", "21", "22", "23", "24", "25", "26a", "26b", "26c", "26d", "27", "28"],
        "section": "NC Form D-400 Individual Income Tax Return - Lines 1-28",
        "transfers_to": None,
    },
]


FORM_100_CA_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37"],
        "section": "CA Form 100 Corporation Franchise or Income Tax Return - Lines 1-37",
        "transfers_to": None,
    },
]


FORM_100S_CA_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40", "41", "42", "43", "44", "44a"],
        "section": "CA Form 100S S Corporation Franchise or Income Tax Return - Lines 1-44a",
        "transfers_to": None,
    },
]


FORM_540_CA_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46", "47", "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59", "60", "61", "62", "63", "64", "65", "71", "72", "73", "74", "75"],
        "section": "CA Form 540 California Resident Income Tax Return - Lines 1-75",
        "transfers_to": None,
    },
]


FORM_IT201_NY_SECTIONS: list[SectionEntry] = [
    {
        "lines": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "19a", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39", "40", "41", "42", "43", "44", "45", "46", "47", "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59", "60", "61", "62", "63", "64", "65", "66", "67", "68", "69", "70", "71", "72", "73", "74", "75", "76", "77"],
        "section": "NY Form IT-201 Resident Income Tax Return - Lines 1-77",
        "transfers_to": None,
    },
]


# ============================================================================
# Registry: maps form canonical name → sections table
# ============================================================================

# Keys match what form_aware_chunker's _detect_form_header sets as current_form
# The chunker looks up sections via FORM_SECTIONS_REGISTRY[current_form]
FORM_SECTIONS_REGISTRY: dict[str, list[SectionEntry]] = {
    # Tier 1
    "Schedule A (Form 1040)": SCHEDULE_A_SECTIONS,
    "Schedule A": SCHEDULE_A_SECTIONS,  # alias (v1 sometimes emits without parent)

    # Tier 2 — Form 1040 family
    "Form 1040": FORM_1040_SECTIONS,
    "Schedule B (Form 1040)": SCHEDULE_B_SECTIONS,
    "Schedule B": SCHEDULE_B_SECTIONS,
    "Schedule D (Form 1040)": SCHEDULE_D_SECTIONS,
    "Schedule D": SCHEDULE_D_SECTIONS,
    "Schedule 1 (Form 1040)": SCHEDULE_1_SECTIONS,
    "Schedule 1": SCHEDULE_1_SECTIONS,
    "Schedule 2 (Form 1040)": SCHEDULE_2_SECTIONS,
    "Schedule 2": SCHEDULE_2_SECTIONS,
    "Schedule 3 (Form 1040)": SCHEDULE_3_SECTIONS,
    "Schedule 3": SCHEDULE_3_SECTIONS,

    # Tier 2 — Forms
    "Form 8889": FORM_8889_SECTIONS,
    "Form 5329": FORM_5329_SECTIONS,
    "Form 8283": FORM_8283_SECTIONS,
    "Form 4562": FORM_4562_SECTIONS,
    "Form 8960": FORM_8960_SECTIONS,
    "Form 8995": FORM_8995_SECTIONS,
    "Form 8995-A": FORM_8995_A_SECTIONS,

    # Tier 3 — S-corp family
    "Form 1120-S": FORM_1120S_SECTIONS,
    "Form 1120S": FORM_1120S_SECTIONS,  # alias (observed in Tracy output)
    "Schedule K": SCHEDULE_K_1120S_SECTIONS,  # 1120S Schedule K
    "Schedule K (Form 1120-S)": SCHEDULE_K_1120S_SECTIONS,
    "Schedule K (Form 1120S)": SCHEDULE_K_1120S_SECTIONS,
    "Schedule K-1": SCHEDULE_K1_1120S_SECTIONS,  # Default to 1120S K-1; 1065 K-1 overrides in Tier 4
    "Schedule K-1 (Form 1120-S)": SCHEDULE_K1_1120S_SECTIONS,
    "Schedule K-1 (Form 1120S)": SCHEDULE_K1_1120S_SECTIONS,
    "Schedule L": SCHEDULE_L_1120S_SECTIONS,
    "Schedule L (Form 1120-S)": SCHEDULE_L_1120S_SECTIONS,
    "Schedule M-1": SCHEDULE_M1_1120S_SECTIONS,
    "Schedule M-1 (Form 1120-S)": SCHEDULE_M1_1120S_SECTIONS,
    "Schedule M-2": SCHEDULE_M2_1120S_SECTIONS,
    "Schedule M-2 (Form 1120-S)": SCHEDULE_M2_1120S_SECTIONS,
    "Form 7203": FORM_7203_SECTIONS,
    "Form 8879-CORP": FORM_8879_CORP_SECTIONS,
    "Form 1125-E": FORM_1125_E_SECTIONS,
    "Form 1125-A": FORM_1125_A_SECTIONS,

    # Tier 4 — Partnerships
    "Form 1065": FORM_1065_SECTIONS,
    "Schedule K (Form 1065)": SCHEDULE_K_1065_SECTIONS,
    "Schedule K (1065)": SCHEDULE_K_1065_SECTIONS,
    "Schedule K-1 (Form 1065)": SCHEDULE_K1_1065_SECTIONS,
    "Schedule K-1 (1065)": SCHEDULE_K1_1065_SECTIONS,

    # Tier 4 — Trusts / Estates
    "Form 1041": FORM_1041_SECTIONS,
    "Schedule K-1 (Form 1041)": SCHEDULE_K1_1041_SECTIONS,
    "Schedule K-1 (1041)": SCHEDULE_K1_1041_SECTIONS,

    # Tier 4 — Info returns
    "W-2": W2_SECTIONS,
    "Form W-2": W2_SECTIONS,
    "Form 1099-INT": FORM_1099_INT_SECTIONS,
    "1099-INT": FORM_1099_INT_SECTIONS,
    "Form 1099-DIV": FORM_1099_DIV_SECTIONS,
    "1099-DIV": FORM_1099_DIV_SECTIONS,
    "Form 1099-B": FORM_1099_B_SECTIONS,
    "1099-B": FORM_1099_B_SECTIONS,
    "Form 1099-R": FORM_1099_R_SECTIONS,
    "1099-R": FORM_1099_R_SECTIONS,
    "Form 1099-MISC": FORM_1099_MISC_SECTIONS,
    "1099-MISC": FORM_1099_MISC_SECTIONS,
    "Form 1099-NEC": FORM_1099_NEC_SECTIONS,
    "1099-NEC": FORM_1099_NEC_SECTIONS,
    "SSA-1099": SSA_1099_SECTIONS,
    "Form SSA-1099": SSA_1099_SECTIONS,

    # Tier 4 — Individual schedules
    "Schedule C (Form 1040)": SCHEDULE_C_SECTIONS,
    "Schedule C": SCHEDULE_C_SECTIONS,
    "Schedule E (Form 1040)": SCHEDULE_E_SECTIONS,
    "Schedule E": SCHEDULE_E_SECTIONS,
    "Schedule F (Form 1040)": SCHEDULE_F_SECTIONS,
    "Schedule F": SCHEDULE_F_SECTIONS,
    "Schedule SE (Form 1040)": SCHEDULE_SE_SECTIONS,
    "Schedule SE": SCHEDULE_SE_SECTIONS,

    # Tier 4 — State returns
    "Form D-400": FORM_D400_NC_SECTIONS,
    "D-400": FORM_D400_NC_SECTIONS,
    "Form 100": FORM_100_CA_SECTIONS,
    "Form 100S": FORM_100S_CA_SECTIONS,
    "Form 540": FORM_540_CA_SECTIONS,
    "Form IT-201": FORM_IT201_NY_SECTIONS,
    "IT-201": FORM_IT201_NY_SECTIONS,
}


def lookup_section_for_line(form: str, line: str) -> Optional[SectionEntry]:
    """Given a form name and a line identifier, return the section entry
    that contains that line, or None if no match.

    Args:
        form: Canonical form name (e.g., "Schedule A (Form 1040)")
        line: Line identifier (e.g., "11", "5d", "1a")

    Returns:
        SectionEntry dict with `lines`, `section`, `transfers_to` fields,
        or None if form unknown or line not in any section.
    """
    sections = FORM_SECTIONS_REGISTRY.get(form)
    if not sections:
        return None
    for entry in sections:
        if line in entry["lines"]:
            return entry
    return None
