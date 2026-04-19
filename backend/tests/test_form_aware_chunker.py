"""Tests for the form-aware chunker module."""

import re

import pytest

from app.services.form_aware_chunker import form_aware_chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pages(*texts: tuple[int, str]) -> list[dict]:
    """Build a pages list from (page_number, text) tuples."""
    return [{"page_number": pn, "text": t} for pn, t in texts]


def _single_page(text: str, page: int = 1) -> list[dict]:
    return [{"page_number": page, "text": text}]


# ===========================================================================
# Form detection (10 tests)
# ===========================================================================


class TestFormDetection:

    def test_form_1040_header_detected(self):
        """Form 1040 header on its own line triggers state change."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "U.S. Individual Income Tax Return\n"
            "Filing Status: Single\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert len(result) >= 1
        assert result[0]["metadata"]["form"] == "Form 1040"

    def test_form_1040sr_variant_detected(self):
        """Form 1040-SR detected as a distinct form."""
        pages = _single_page(
            "Form 1040-SR (2024)\n"
            "U.S. Tax Return for Seniors\n"
            "Filing Status: Married Filing Jointly\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["form"] == "Form 1040-SR"

    def test_form_1040x_amended_detected(self):
        """Form 1040-X (amended return) detected."""
        pages = _single_page(
            "Form 1040-X\n"
            "Amended U.S. Individual Income Tax Return\n"
            "Original return filed: 04/15/2024\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["form"] == "Form 1040-X"

    def test_schedule_a_with_parent_form(self):
        """Schedule A (Form 1040) detected with parent form."""
        pages = _single_page(
            "Schedule A (Form 1040)\n"
            "Itemized Deductions\n"
            "Medical and Dental Expenses\n"
            "Line 1: Medical expenses: $5,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["form"] == "Schedule A (Form 1040)"
        assert result[0]["metadata"]["parent_form"] == "Form 1040"

    def test_schedule_b_with_parent_form(self):
        """Schedule B (Form 1040) detected with parent form."""
        pages = _single_page(
            "Schedule B (Form 1040)\n"
            "Interest and Ordinary Dividends\n"
            "Part I Interest\n"
            "1. Wells Fargo Bank: $1,200\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        # First chunk is the header, may include Part I depending on sizing
        forms = {r["metadata"]["form"] for r in result}
        assert "Schedule B (Form 1040)" in forms

    def test_schedule_d_detected(self):
        """Schedule D detected."""
        pages = _single_page(
            "Schedule D (Form 1040)\n"
            "Capital Gains and Losses\n"
            "Part I Short-Term Capital Gains and Losses\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        forms = {r["metadata"]["form"] for r in result}
        assert "Schedule D (Form 1040)" in forms

    def test_form_5329_standalone_detected(self):
        """Form 5329 (standalone 4-digit form) detected."""
        pages = _single_page(
            "Form 5329\n"
            "Additional Taxes on Qualified Plans\n"
            "Part I Additional Tax on Early Distributions\n"
            "Line 1: Early distributions included in income: $10,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        forms = {r["metadata"]["form"] for r in result}
        assert "Form 5329" in forms

    def test_form_8889_detected(self):
        """Form 8889 (HSA) detected."""
        pages = _single_page(
            "Form 8889\n"
            "Health Savings Accounts (HSAs)\n"
            "Part I HSA Contributions and Deductions\n"
            "Line 2: HSA contributions you made for 2024: $4,150\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        forms = {r["metadata"]["form"] for r in result}
        assert "Form 8889" in forms

    def test_state_form_d400_detected(self):
        """D-400 North Carolina state form detected."""
        pages = _single_page(
            "D-400 Individual Income Tax Return\n"
            "North Carolina Department of Revenue\n"
            "Filing Status: Single\n"
            "Federal Adjusted Gross Income: $85,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        # State form should be detected
        assert result[0]["metadata"]["form"] != "Unknown"
        assert "D-400" in result[0]["metadata"]["form"]

    def test_form_1040es_without_future_year_still_detected_as_voucher_form(self):
        """Form 1040-ES header without a future year: form detected but not flagged as voucher.

        The line-level form detector sets current_form to 'Form 1040-ES',
        but detect_voucher_chunk returns is_voucher=False because there
        is no future year in the text.
        """
        pages = _single_page(
            "Form 1040-ES\n"
            "Estimated Tax Worksheet\n"
            "Line 1: Expected AGI: $100,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert len(result) >= 1
        assert result[0]["metadata"]["form"] == "Form 1040-ES"
        assert result[0]["metadata"]["is_voucher"] is False

    def test_form_header_followed_by_title_accepted(self):
        """'Form 8889 Health Savings Accounts' at start of line is a real header."""
        pages = _single_page(
            "Form 8889 Health Savings Accounts (HSAs)\n"
            "Part I HSA Contributions and Deductions\n"
            "Line 2: HSA contributions: $4,150\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["form"] == "Form 8889"

    def test_form_header_alone_on_line_accepted(self):
        """'Form 5329' alone on a line is accepted as a form header."""
        pages = _single_page(
            "Form 5329\n"
            "Additional Taxes on Qualified Plans\n"
            "Line 1: Early distributions: $10,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["form"] == "Form 5329"

    def test_mid_sentence_form_reference_no_state_change(self):
        """'Form 8283' mid-sentence does NOT trigger state change."""
        pages = _single_page(
            "Schedule A (Form 1040)\n"
            "Itemized Deductions\n"
            "Noncash contributions over $500 require Form 8283 to be attached.\n"
            "Total charitable contributions: $15,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        # All chunks should remain Schedule A — Form 8283 is mid-sentence
        for chunk in result:
            assert chunk["metadata"]["form"] == "Schedule A (Form 1040)"

    def test_year_only_match_rejected(self):
        """'Form 2024' (OCR artifact from garbled 'Form 8949 (2024)') must not
        be detected as a real form. Years 1900-2099 are never IRS form numbers."""
        pages = _single_page(
            "Form 2024\n"
            "File with your Schedule D to list your transactions for lines 1b, 2, 3, 8b, 9, and 10 of Schedule D.\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert chunk["metadata"]["form"] != "Form 2024", (
                "Year-as-form 'Form 2024' should be rejected"
            )

    def test_form_8949_header_still_detected(self):
        """Form 8949 is a real form and must still be detected after year rejection fix."""
        pages = _single_page(
            "Form 8949\n"
            "Sales and Other Dispositions of Capital Assets\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["form"] == "Form 8949"

    def test_state_form_p_28_rejected(self):
        """'P 28.0 ...' is a Form 8949 transaction line, not a state form."""
        pages = _single_page(
            "P 28.0 12/16/24 12/17/24 2,651. 2,693. -42.\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert "P 28" not in chunk["metadata"]["form"], (
                f"'P 28' falsely detected as form: {chunk['metadata']['form']}"
            )

    def test_state_form_rev_12_rejected(self):
        """'REV 12/10/24 INTUIT.CG.CFP.SP' is a TurboTax footer, not a state form."""
        pages = _single_page(
            "REV 12/10/24 INTUIT.CG.CFP.SP\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert "REV" not in chunk["metadata"]["form"], (
                f"'REV 12' falsely detected as form: {chunk['metadata']['form']}"
            )

    def test_d400_still_detected(self):
        """D-400 must still be detected after switching to state form whitelist."""
        pages = _single_page(
            "D-400 Individual Income Tax Return\n"
            "North Carolina Department of Revenue\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert "D-400" in result[0]["metadata"]["form"]

    def test_schedule_a_form_8936_detected_with_correct_parent(self):
        """Schedule A (Form 8936) detected with parent_form = 'Form 8936'."""
        pages = _single_page(
            "Schedule A (Form 8936)\n"
            "Clean Vehicle Credit Amount\n"
            "Line 1: Tentative credit: $7,500\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["form"] == "Schedule A (Form 8936)"
        assert result[0]["metadata"]["parent_form"] == "Form 8936"


# ===========================================================================
# Section detection (5 tests)
# ===========================================================================


class TestSectionDetection:

    def test_part_i_interest_triggers_section(self):
        """'Part I Interest' triggers a new section within Schedule B."""
        pages = _single_page(
            "Schedule B (Form 1040)\n"
            "Interest and Ordinary Dividends\n\n"
            "Part I Interest\n"
            "1. Chase Bank: $500\n"
            "2. Savings account: $200\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        sections = [r["metadata"]["section"] for r in result]
        assert any("Part I" in s for s in sections)

    def test_part_ii_ordinary_dividends_triggers_section(self):
        """'Part II Ordinary Dividends' triggers new section after Part I."""
        pages = _single_page(
            "Schedule B (Form 1040)\n"
            "Interest and Ordinary Dividends\n\n"
            "Part I Interest\n"
            "1. Chase Bank: $500\n\n"
            "Part II Ordinary Dividends\n"
            "5. Vanguard Total Stock: $1,200\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        sections = [r["metadata"]["section"] for r in result]
        assert any("Part II" in s for s in sections)

    def test_gifts_to_charity_heading_detected(self):
        """'Gifts to Charity' line-group heading detected on Schedule A."""
        pages = _single_page(
            "Schedule A (Form 1040)\n"
            "Itemized Deductions\n\n"
            "Gifts to Charity\n"
            "Line 11: Gifts by cash or check: $5,000\n"
            "Line 12: Other than cash or check: $2,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        sections = [r["metadata"]["section"] for r in result]
        assert any("Gifts to Charity" in s for s in sections)

    def test_income_heading_detected_on_1040(self):
        """'Income' heading detected on Form 1040."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "U.S. Individual Income Tax Return\n\n"
            "Income\n"
            "Line 1a: Wages, salaries, tips: $145,000\n"
            "Line 2b: Taxable interest: $3,200\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        sections = [r["metadata"]["section"] for r in result]
        assert any("Income" in s for s in sections)

    def test_schedule_b_part_iii_foreign_accounts(self):
        """Schedule B Part III detected as a part/section boundary."""
        pages = _single_page(
            "Schedule B (Form 1040)\n"
            "Interest and Ordinary Dividends\n\n"
            "Part III Foreign Accounts and Trusts\n"
            "7a. At any time during 2024, did you have a financial interest\n"
            "in or a signature authority over a financial account in a\n"
            "foreign country? Yes / No\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        # At least one chunk should reference Part III in part or section
        has_part_iii = any(
            ("Part III" in (r["metadata"].get("part") or ""))
            or ("Part III" in (r["metadata"].get("section") or ""))
            for r in result
        )
        assert has_part_iii, (
            f"No chunk has Part III in part or section. "
            f"Parts: {[r['metadata'].get('part') for r in result]}, "
            f"Sections: {[r['metadata'].get('section') for r in result]}"
        )

    def test_section_change_closes_chunk(self):
        """Section change within a form closes current chunk and starts new one."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "U.S. Individual Income Tax Return\n\n"
            "Income\n"
            "Line 1a: Wages: $145,000\n"
            "Line 2b: Interest: $3,200\n\n"
            "Adjusted Gross Income\n"
            "Line 11: Adjusted gross income: $148,200\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        sections = [r["metadata"]["section"] for r in result]
        assert "Income" in sections
        assert "Adjusted Gross Income" in sections
        # They must be separate chunks
        income_idx = sections.index("Income")
        agi_idx = sections.index("Adjusted Gross Income")
        assert income_idx != agi_idx


# ===========================================================================
# State inheritance (3 tests)
# ===========================================================================


class TestStateInheritance:

    def test_form_spans_two_pages(self):
        """Form spanning 2 pages: page 2 content inherits form identity.

        When page 2 has no form header and no boundary trigger fires, its
        content may be merged into the preceding chunk.  The key invariant
        is that ALL chunks containing page-2 text carry the Schedule B
        form identity (state inheritance).
        """
        # Make page 1 large enough to force a separate chunk for page 2
        page1_lines = (
            "Schedule B (Form 1040)\n"
            "Interest and Ordinary Dividends\n\n"
            "Part I Interest\n"
            + "".join(f"{i}. Bank #{i}: ${i * 100}\n" for i in range(1, 30))
        )
        pages = _pages(
            (5, page1_lines),
            (6, (
                "30. Wells Fargo: $700\n"
                "31. Ally Bank: $300\n"
                "32. Total: $31,500\n"
            )),
        )
        result = form_aware_chunk(pages, tax_year=2024)
        # All chunks must carry Schedule B form identity
        for chunk in result:
            assert chunk["metadata"]["form"] == "Schedule B (Form 1040)"
        # At least one chunk should contain page 6 content
        all_text = " ".join(r["text"] for r in result)
        assert "Wells Fargo" in all_text

    def test_voucher_sequence_across_pages(self):
        """Voucher sequence across multiple pages: all tagged as voucher."""
        pages = _pages(
            (20, (
                "Form 1040-ES\n"
                "2025 Estimated Tax Payment Voucher 1\n"
                "Calendar year—Due April 15, 2025\n"
                "Amount: $12,500\n"
            )),
            (21, (
                "Form 1040-ES\n"
                "2025 Estimated Tax Payment Voucher 2\n"
                "Calendar year—Due June 15, 2025\n"
                "Amount: $12,500\n"
            )),
            (22, (
                "Form 1040-ES\n"
                "2025 Estimated Tax Payment Voucher 3\n"
                "Calendar year—Due September 15, 2025\n"
                "Amount: $12,500\n"
            )),
            (23, (
                "Form 1040-ES\n"
                "2025 Estimated Tax Payment Voucher 4\n"
                "Calendar year—Due January 15, 2026\n"
                "Amount: $12,500\n"
            )),
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert len(result) == 4
        for chunk in result:
            assert chunk["metadata"]["is_voucher"] is True

    def test_after_voucher_form_1040_detected(self):
        """After voucher sequence ends and Form 1040 appears, state transitions."""
        pages = _pages(
            (20, (
                "Form 1040-ES\n"
                "2025 Estimated Tax Payment Voucher 1\n"
                "Calendar year—Due April 15, 2025\n"
                "Amount: $12,500\n"
            )),
            (21, (
                "Form 1040 (2024)\n"
                "U.S. Individual Income Tax Return\n"
                "Filing Status: Single\n"
            )),
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert len(result) >= 2
        # First chunk is voucher
        assert result[0]["metadata"]["is_voucher"] is True
        # Last chunk should be Form 1040, not voucher
        last = result[-1]
        assert last["metadata"]["form"] == "Form 1040"
        assert last["metadata"]["is_voucher"] is False


# ===========================================================================
# Cross-references (3 tests)
# ===========================================================================


class TestCrossReferences:

    def test_attach_sch_b_no_state_change(self):
        """'Attach Sch. B if required' on Form 1040 does NOT change state."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "U.S. Individual Income Tax Return\n"
            "Line 2b: Taxable interest. Attach Sch. B if required: $3,200\n"
            "Line 3a: Qualified dividends: $1,500\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert chunk["metadata"]["form"] == "Form 1040"

    def test_from_schedule_a_no_state_change(self):
        """'from Schedule A' mid-paragraph does NOT change state."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "U.S. Individual Income Tax Return\n"
            "Line 12: Itemized deductions from Schedule A, or standard deduction: $14,600\n"
            "Line 13: Qualified business income deduction: $0\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert chunk["metadata"]["form"] == "Form 1040"

    def test_form_1040_line_2b_reference_no_state_change(self):
        """'on Form 1040 or 1040-SR, line 2b' on Schedule B does NOT change state."""
        pages = _single_page(
            "Schedule B (Form 1040)\n"
            "Interest and Ordinary Dividends\n"
            "Line 4: Add lines 1 through 3. Enter here and on Form 1040 or 1040-SR, line 2b: $3,200\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert chunk["metadata"]["form"] == "Schedule B (Form 1040)"

    def test_form_reference_at_start_of_continuation_line(self):
        """OCR line-wrap puts 'Form 8283' at start of a continuation line.

        This is a cross-reference, not a form header — all chunks must
        remain Schedule A.
        """
        pages = _single_page(
            "Schedule A (Form 1040)\n"
            "Itemized Deductions\n"
            "Charitable contributions over $500 require\n"
            "Form 8283 to be attached with documentation.\n"
            "Total charitable contributions: $15,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert chunk["metadata"]["form"] == "Schedule A (Form 1040)", (
                f"Expected Schedule A but got {chunk['metadata']['form']!r} — "
                f"'Form 8283' at start of continuation line triggered state change"
            )

    def test_form_1099_div_reference_rejected(self):
        """'Form 1099-DIV or substitute statement' is a cross-reference, not a header.

        The lowercase 'or' after the form ID triggers the continuation rejection rule.
        """
        pages = _single_page(
            "Schedule B (Form 1040)\n"
            "Part I Interest\n"
            "Form 1099-DIV or substitute statement from a brokerage firm\n"
            "list the firm's name as the payer.\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        for chunk in result:
            assert chunk["metadata"]["form"] == "Schedule B (Form 1040)", (
                f"Expected Schedule B but got {chunk['metadata']['form']!r} — "
                f"'Form 1099-DIV or ...' triggered false state change"
            )


# ===========================================================================
# Prefix format (2 tests)
# ===========================================================================


class TestPrefixFormat:

    def test_prefix_matches_exact_pattern(self):
        """Prefix exactly matches '[TAX YEAR YYYY | Form: X | Page N | Section: Y]'."""
        pages = _single_page(
            "Schedule A (Form 1040)\n"
            "Itemized Deductions\n"
            "Line 5: State and local taxes: $10,000\n",
            page=7,
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert len(result) >= 1
        text = result[0]["text"]
        # First line is the prefix
        prefix_line = text.split("\n")[0]
        pattern = re.compile(
            r"^\[TAX YEAR \d{4} \| Form: .+ \| Page \d+ \| Section: .+\]$"
        )
        assert pattern.match(prefix_line), f"Prefix doesn't match pattern: {prefix_line!r}"

    def test_prefix_unknown_tax_year(self):
        """When tax_year is None, prefix uses 'TAX YEAR UNKNOWN'."""
        pages = _single_page(
            "Form 1040\n"
            "U.S. Individual Income Tax Return\n"
        )
        result = form_aware_chunk(pages, tax_year=None)
        assert len(result) >= 1
        prefix_line = result[0]["text"].split("\n")[0]
        assert "TAX YEAR UNKNOWN" in prefix_line


# ===========================================================================
# Metadata shape (2 tests)
# ===========================================================================


class TestMetadataShape:

    REQUIRED_FIELDS = {
        "doc_type", "tax_year", "form", "parent_form", "page",
        "section", "part", "lines_covered", "transfers_to",
        "is_voucher", "voucher_continuation", "chunker_version",
    }

    def test_all_required_fields_present(self):
        """All required metadata fields are present for tax_return chunks."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "U.S. Individual Income Tax Return\n"
            "Line 1a: Wages: $145,000\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert len(result) >= 1
        metadata = result[0]["metadata"]
        missing = self.REQUIRED_FIELDS - set(metadata.keys())
        assert not missing, f"Missing metadata fields: {missing}"
        assert metadata["doc_type"] == "tax_return"

    def test_chunker_version(self):
        """chunker_version is 'form_aware_v1'."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "U.S. Individual Income Tax Return\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        assert result[0]["metadata"]["chunker_version"] == "form_aware_v1"


# ===========================================================================
# Boundary alignment (1 test)
# ===========================================================================


class TestBoundaryAlignment:

    def test_form_boundary_forces_chunk_split_mid_content(self):
        """New form header mid-page closes previous form's chunk, starts new one."""
        pages = _single_page(
            "Form 1040 (2024)\n"
            "Line 20: Amount from Schedule 3, line 8: $500\n"
            "Line 21: Add lines 19 and 20: $500\n"
            "Line 22: Subtract line 21 from line 18: $40,000\n"
            "\n"
            "Form 8889\n"
            "Health Savings Accounts (HSAs)\n"
            "Part I HSA Contributions and Deductions\n"
            "Line 2: HSA contributions: $4,150\n"
        )
        result = form_aware_chunk(pages, tax_year=2024)
        forms = [r["metadata"]["form"] for r in result]
        assert len(result) >= 2, f"Expected >= 2 chunks but got {len(result)}: {forms}"
        assert "Form 1040" in forms, f"No Form 1040 chunk found in {forms}"
        assert "Form 8889" in forms, f"No Form 8889 chunk found in {forms}"
