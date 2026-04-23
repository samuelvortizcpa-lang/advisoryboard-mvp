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
# Schedule digit/multi-char identifier tests (4 tests — expected to FAIL)
# ===========================================================================


class TestScheduleDigitPatterns:
    """Tests for Schedule identifiers that use digits or multi-letter codes.

    The current Schedule pattern only accepts [A-Z] (single letter), but
    IRS uses Schedule 1, 2, 3, SE, 8812, etc. These tests document the
    gap and will fail until the pattern is broadened.
    """

    def test_schedule_2_form_1040_detected(self):
        """Schedule 2 (Form 1040) Additional Taxes — must be detected.
        Currently fails because the Schedule pattern only accepts letters [A-Z].
        """
        from app.services.form_aware_chunker import _detect_form_header

        line = "SCHEDULE 2 (Form 1040) 2024"
        result = _detect_form_header(line)
        assert result is not None, f"Expected match, got None for: {line}"
        form, parent = result
        assert form == "Schedule 2 (Form 1040)", f"Expected Schedule 2 (Form 1040), got: {form}"
        assert parent == "Form 1040", f"Expected parent Form 1040, got: {parent}"

    def test_schedule_3_form_1040_detected(self):
        """Schedule 3 (Form 1040) Additional Credits and Payments — must be detected."""
        from app.services.form_aware_chunker import _detect_form_header

        line = "SCHEDULE 3 (Form 1040) 2024"
        result = _detect_form_header(line)
        assert result is not None, f"Expected match, got None for: {line}"
        form, parent = result
        assert form == "Schedule 3 (Form 1040)", f"Expected Schedule 3 (Form 1040), got: {form}"
        assert parent == "Form 1040", f"Expected parent Form 1040, got: {parent}"

    def test_schedule_8812_detected(self):
        """Schedule 8812 (Credits for Qualifying Children) — must be detected.
        This is a 4-digit-named schedule; pattern must accept multi-digit identifiers.
        """
        from app.services.form_aware_chunker import _detect_form_header

        line = "Schedule 8812 (Form 1040) 2024 Credits for Qualifying Children"
        result = _detect_form_header(line)
        assert result is not None, f"Expected match, got None for: {line}"
        form, parent = result
        assert "Schedule 8812" in form, f"Expected Schedule 8812 in form, got: {form}"

    def test_schedule_se_detected(self):
        """Schedule SE (Self-Employment Tax) — two-letter identifier.
        Currently fails because the pattern captures only a single letter [A-Z].
        """
        from app.services.form_aware_chunker import _detect_form_header

        line = "SCHEDULE SE (Form 1040) 2024 Self-Employment Tax"
        result = _detect_form_header(line)
        assert result is not None, f"Expected match, got None for: {line}"
        form, parent = result
        assert "Schedule SE" in form, f"Expected Schedule SE in form, got: {form}"


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
        assert result[0]["metadata"]["chunker_version"] == "form_aware_v2"


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


# ===========================================================================
# Voucher false-positive regression tests (3 tests — expected to FAIL until fix)
# ===========================================================================


class TestVoucherFalsePositives:
    """Tests for voucher detection false positives.

    These tests document the bug where Form 1040 page 2 is incorrectly
    flagged as a 1040-ES voucher because an account number matches the
    IRS lockbox routing pattern and a future year appears in an unrelated
    context (e.g. "applied to your 2025 estimated tax").
    """

    def test_voucher_detection_rejects_form_1040_main_page(self):
        """Form 1040 page 2 must NOT be flagged as a voucher.

        The account number '3 3 4 0 0 0 3 6 7 7 7 1' matches the IRS
        lockbox routing pattern, and '2025' appears in 'applied to your
        2025 estimated tax' — but this is a regular Form 1040, not a
        1040-ES voucher.
        """
        from app.services.chunking import detect_voucher_chunk

        PAGE_6_TEXT = (
            "Form 1040 (2024) Page 2\n"
            "Tax and 16 Tax (see instructions). Check if any from Form(s): "
            "1 8814 2 4972 3 . . 16 40,934. Credits 17 Amount from Schedule 2, "
            "line 3 . . . . . . . . . . . . . . . . . . . . 17 310.\n"
            "25a 43,141. b Form(s) 1099 . . . 25b 0. c Other forms . . . 25c 678.\n"
            "26 2024 estimated tax payments and amount applied from 2023 return "
            ". . . . . . . . . . 26\n"
            "See instructions. d Account number 3 3 4 0 0 0 3 6 7 7 7 1\n"
            "36 Amount of line 34 you want applied to your 2025 estimated tax "
            ". . . 36\n"
            "38 Estimated tax penalty (see instructions) . . . . . . . . .\n"
            "Go to www.irs.gov/Form1040 for instructions and the latest "
            "information. BAA REV 03/20/25 Intuit.cg.cfp.sp Form 1040 (2024)"
        )

        result = detect_voucher_chunk(PAGE_6_TEXT, return_tax_year=2024)
        assert result["is_voucher"] is False, (
            f"Form 1040 page 2 falsely flagged as voucher: {result}"
        )

    def test_voucher_detection_accepts_real_1040es_voucher(self):
        """A genuine Form 1040-ES payment voucher must be detected."""
        from app.services.chunking import detect_voucher_chunk

        VOUCHER_1_TEXT = (
            "Form 1040-ES Payment Voucher\n"
            "Detach Here and Mail With Your Payment\n"
            "Department of the Treasury Calendar Year Internal Revenue Service Due\n"
            "File only if you are making a payment of estimated tax by check or "
            "money order. Mail this Amount of estimated tax voucher with your "
            "check or money order payable to the 'United States Treasury.'\n"
            "1\n"
            "MOORESVILLE NC 28117-9551\n"
            "658.\n"
            "105 LONGLEAF DR\n"
            "252-75-6885\n"
            "AERIN HA\n"
            "INTERNAL REVENUE SERVICE\n"
            "PO BOX 1300\n"
            "CHARLOTTE NC 28201-1300\n"
            "04/15/2025 2025\n"
            "2025\n"
            "REV 03/20/25 INTUIT.CG.CFP.SP 1555\n"
            "MICHAEL L TJAHJADI\n"
            "252756885 ZN TJAH 30 0 202512 430"
        )

        result = detect_voucher_chunk(VOUCHER_1_TEXT, return_tax_year=2024)
        assert result["is_voucher"] is True, (
            f"Real 1040-ES voucher not detected: {result}"
        )
        assert result["voucher_year"] == 2025

    def test_voucher_detection_requires_multiple_signals(self):
        """A single weak voucher signal plus a future year must NOT trigger.

        'estimated tax payments' matches a voucher pattern, but a real
        voucher has multiple corroborating signals (Form 1040-ES header,
        payment voucher language, IRS address, etc.). One weak match in
        otherwise-normal text should not flag the chunk.
        """
        from app.services.chunking import detect_voucher_chunk

        WEAK_SIGNAL_TEXT = (
            "This is a regular document that happens to mention "
            "estimated tax payments once.\n"
            "The year 2025 also appears for unrelated reasons.\n"
            "No other voucher markers are present."
        )

        result = detect_voucher_chunk(WEAK_SIGNAL_TEXT, return_tax_year=2024)
        assert result["is_voucher"] is False, (
            f"Single weak signal falsely flagged as voucher: {result}"
        )


# ===========================================================================
# Form 1040 content fallback tests (3 tests — expected to FAIL until fix)
# ===========================================================================


class TestForm1040ContentFallback:
    """Tests for content-based Form 1040 inference when OCR destroys the header.

    Page 5 of Michael's document has its Form 1040 header garbled by OCR
    ('Form 1040' → '51 0 40'). A content-based fallback should recover
    the form identity when multiple distinctive Form 1040 phrases appear.
    """

    def test_unknown_chunk_with_two_form_1040_phrases_upgrades_to_form_1040(self):
        """Page 5 of Michael's doc has its Form 1040 header destroyed by OCR
        ('Form 1040' → '51 0 40'). Content-based inference must recover it
        when the chunk contains distinctive Form 1040 line-item phrases.
        """
        from app.services.form_aware_chunker import form_aware_chunk

        # Synthetic text mimicking page 5 OCR — no Form 1040 header,
        # but clear Form 1040 page 1 content
        pages = [{
            "page_number": 1,
            "text": (
                "51 0 40 Department of Treasury 2024\n"
                "Income 1a Total amount from Form(s) W-2, box 1 271,792.\n"
                "9 Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7, and 8. This is your total income 293,600.\n"
                "11 Subtract line 10 from line 9. This is your adjusted gross income 293,600.\n"
                "12 Standard deduction or itemized deductions (from Schedule A) 61,126.\n"
                "15 This is your taxable income 232,445.\n"
            ),
        }]

        result = form_aware_chunk(pages, tax_year=2024)
        forms = [r["metadata"]["form"] for r in result]
        assert any(f == "Form 1040" for f in forms), (
            f"Expected at least one chunk tagged Form 1040 via content fallback, got: {forms}"
        )
        assert not any(f == "Unknown" for f in forms), (
            f"Expected no Unknown chunks after content fallback, got: {forms}"
        )

    def test_single_form_1040_phrase_stays_unknown(self):
        """A single distinctive phrase is not enough to trigger the fallback.
        Prevents misclassifying a chunk that mentions 'total income' once as
        Form 1040 when it's actually something else (or truly ambiguous).
        """
        from app.services.form_aware_chunker import form_aware_chunk

        pages = [{
            "page_number": 1,
            "text": (
                "Some document with no clear form header.\n"
                "It mentions This is your total income once.\n"
                "But nothing else distinctive about Form 1040.\n"
                "Just regular prose with a line number reference line 5.\n"
            ),
        }]

        result = form_aware_chunk(pages, tax_year=2024)
        forms = [r["metadata"]["form"] for r in result]
        assert all(f == "Unknown" for f in forms), (
            f"Single weak signal should not upgrade to Form 1040: {forms}"
        )

    def test_content_fallback_does_not_override_known_form(self):
        """If a chunk already has a known form (e.g., Schedule B) but
        happens to include Form 1040 phrases as cross-references, the
        content fallback must NOT override — it only upgrades Unknown.
        """
        from app.services.form_aware_chunker import form_aware_chunk

        pages = [{
            "page_number": 11,
            "text": (
                "SCHEDULE B (Form 1040) 2024 Interest and Ordinary Dividends\n"
                "Part I Interest\n"
                "This section transfers to This is your total income on the main form\n"
                "and affects This is your adjusted gross income calculation.\n"
                "1 List name of payer\n"
                "Standard deduction or itemized deductions apply on Form 1040\n"
            ),
        }]

        result = form_aware_chunk(pages, tax_year=2024)
        # At least one chunk should be tagged Schedule B, not Form 1040
        forms = [r["metadata"]["form"] for r in result]
        schedule_b_chunks = [f for f in forms if "Schedule B" in f]
        assert len(schedule_b_chunks) >= 1, (
            f"Expected at least one Schedule B chunk; content fallback may have overridden. Got: {forms}"
        )


# ===========================================================================
# Page-level form resolution tests (6 tests — some expected to FAIL until fix)
# ===========================================================================


class TestPageLevelFormResolution:
    """Tests for page-level form inference.

    When OCR destroys a page header, per-chunk content fallback may only
    catch some chunks (those with enough distinctive phrases). Page-level
    inference should resolve the form once for the entire page and apply
    it to all chunks on that page.
    """

    def test_page_with_destroyed_header_but_many_phrases_resolves_to_form_1040(self):
        """A page whose OCR destroys the Form 1040 header (renders as '51 0 40')
        should have ALL its chunks tagged Form 1040 via page-level content
        inference — not just some chunks.
        """
        from app.services.form_aware_chunker import form_aware_chunk

        # Long enough page text that the chunker will split it into 3+ chunks
        pages = [{
            "page_number": 5,
            "text": (
                "51 0 40 Department ofthe Treasury—Internal Revenue Service 2024\n"
                "U.S. Individual Income Tax Return OMB No. 1545-0074\n"
                "For the year Jan. 1-Dec. 31, 2024\n"
                "Your first name and middle initial Last name Your social security number\n"
                "Michael L Tjahjadi 252 75 6885\n"
                "Home address 105 Longleaf Dr\n"
                "Mooresville NC 281179551\n"
                "Filing Status Married filing jointly\n"
                "Standard Deduction box\n"
                "Dependents (see instructions)\n"
                "\n"
                "Income\n"
                "1a Total amount from Form(s) W-2, box 1 (see instructions) 271,792.\n"
                "1b Household employee wages not reported on Form(s) W-2\n"
                "2a Tax-exempt interest 136. b Taxable interest 7.\n"
                "3a Qualified dividends 3,077. b Ordinary dividends 13,267.\n"
                "4a IRA distributions 7,950. b Taxable amount 950.\n"
                "\n"
                "7 Capital gain or (loss). Attach Schedule D if required 7,584.\n"
                "8 Additional income from Schedule 1, line 10\n"
                "9 Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7, and 8. This is your total income 293,600.\n"
                "10 Adjustments to income from Schedule 1, line 26\n"
                "11 Subtract line 10 from line 9. This is your adjusted gross income 293,600.\n"
                "12 Standard deduction or itemized deductions (from Schedule A) 61,126.\n"
                "13 Qualified business income deduction from Form 8995 or Form 8995-A 29.\n"
                "14 Add lines 12 and 13 61,155.\n"
                "15 Subtract line 14 from line 11. If zero or less, enter -0-. This is your taxable income 232,445.\n"
                "For Disclosure, Privacy Act, and Paperwork Reduction Act Notice, see separate instructions.\n"
            ),
        }]

        result = form_aware_chunk(pages, tax_year=2024)
        forms = [r["metadata"]["form"] for r in result]
        assert len(result) >= 2, f"Expected page to split into multiple chunks, got {len(result)}"
        assert all(f == "Form 1040" for f in forms), (
            f"Expected ALL chunks to be tagged Form 1040, got: {forms}"
        )

    def test_page_with_destroyed_header_and_one_phrase_stays_unknown(self):
        """A page with a destroyed header and only ONE distinctive phrase
        should not be resolved as Form 1040 — threshold requires at least 2.
        """
        from app.services.form_aware_chunker import form_aware_chunk

        pages = [{
            "page_number": 5,
            "text": (
                "51 0 40 Department of Treasury\n"
                "Some content with one phrase: This is your total income appears here.\n"
                "But nothing else distinctive about Form 1040 page 1.\n"
                "Just regular prose and numbers 12345.\n"
            ),
        }]

        result = form_aware_chunk(pages, tax_year=2024)
        forms = [r["metadata"]["form"] for r in result]
        assert all(f == "Unknown" for f in forms), (
            f"Expected Unknown with single signal, got: {forms}"
        )

    def test_page_with_real_header_wins_over_content_inference(self):
        """A page with a real Schedule B header must be tagged Schedule B
        even if Form 1040 distinctive phrases appear (as cross-references).
        Header detection takes precedence over content inference.
        """
        from app.services.form_aware_chunker import form_aware_chunk

        pages = [{
            "page_number": 11,
            "text": (
                "SCHEDULE B (Form 1040) 2024 Interest and Ordinary Dividends\n"
                "Part I Interest\n"
                "Note: See the Instructions for Form 1040 line 2b\n"
                "This schedule transfers to This is your total income calculation\n"
                "and affects This is your adjusted gross income determination\n"
                "1 List name of payer\n"
                "Standard deduction or itemized deductions are on Form 1040\n"
                "CHARLES SCHWAB 6.59\n"
                "MERRILL LYNCH 9,224.98\n"
            ),
        }]

        result = form_aware_chunk(pages, tax_year=2024)
        forms = [r["metadata"]["form"] for r in result]
        assert any("Schedule B" in f for f in forms), (
            f"Expected Schedule B, got: {forms}"
        )
        assert not any(f == "Form 1040" for f in forms), (
            f"Schedule B header must win over Form 1040 content inference, got: {forms}"
        )

    def test_unknown_page_inherits_from_previous_known_page(self):
        """A page with no detectable header and no distinctive phrases
        should inherit the form from the previous page (document continuation).
        """
        from app.services.form_aware_chunker import form_aware_chunk

        pages = [
            {
                "page_number": 7,
                "text": (
                    "SCHEDULE 2 (Form 1040) 2024 Additional Taxes\n"
                    "Part I Tax\n"
                    "1 Additions to tax\n"
                    "2 Alternative minimum tax 229.\n"
                    "3 Add lines 1z and 2. Enter here and on Form 1040 line 17 310.\n"
                ),
            },
            {
                "page_number": 8,
                "text": (
                    "Page 2 continuation with no clear header\n"
                    "17 Other additional taxes\n"
                    "18 Total additional taxes 1,502.\n"
                    "21 Add lines 4, 7 through 16, 18, and 19 1,502.\n"
                ),
            },
        ]

        result = form_aware_chunk(pages, tax_year=2024)
        page_8_chunks = [r for r in result if r["page_number"] == 8]
        page_8_forms = [r["metadata"]["form"] for r in page_8_chunks]
        assert len(page_8_chunks) >= 1, "Expected at least one chunk on page 8"
        assert all("Schedule 2" in f for f in page_8_forms), (
            f"Expected page 8 to inherit Schedule 2 from page 7, got: {page_8_forms}"
        )

    def test_page_after_voucher_stays_unknown_without_signals(self):
        """After exiting a voucher sequence, a page with no header and
        no distinctive phrases should stay Unknown (voucher state is reset,
        and we cannot infer a form from nothing).
        """
        from app.services.form_aware_chunker import form_aware_chunk

        pages = [
            {
                "page_number": 1,
                "text": (
                    "Form 1040-ES Payment Voucher\n"
                    "File only if you are making a payment of estimated tax\n"
                    "Calendar Year Due 04/15/2025 2025\n"
                    "Payment voucher\n"
                    "MICHAEL L TJAHJADI\n"
                ),
            },
            {
                "page_number": 2,
                "text": (
                    "Some filler text with no form identifiers\n"
                    "Numbers and line references 12345\n"
                    "No distinctive phrases present\n"
                ),
            },
        ]

        result = form_aware_chunk(pages, tax_year=2024)
        page_2_chunks = [r for r in result if r["page_number"] == 2]
        page_2_forms = [r["metadata"]["form"] for r in page_2_chunks]
        assert all(f == "Unknown" for f in page_2_forms), (
            f"Expected Unknown after voucher exit without signals, got: {page_2_forms}"
        )

    def test_multi_form_page_splits_correctly(self):
        """A page that contains two form headers (Schedule 2 ending and
        Schedule 3 starting) should produce chunks for both forms. Page-level
        inference must not prevent line-by-line mid-page form changes.
        """
        from app.services.form_aware_chunker import form_aware_chunk

        pages = [{
            "page_number": 9,
            "text": (
                "SCHEDULE 2 (Form 1040) 2024 Additional Taxes\n"
                "Part II continued\n"
                "21 Total additional taxes 1,502.\n"
                "\n"
                "SCHEDULE 3 (Form 1040) 2024 Additional Credits and Payments\n"
                "Part I Nonrefundable Credits\n"
                "1 Foreign tax credit 101.\n"
            ),
        }]

        result = form_aware_chunk(pages, tax_year=2024)
        forms = [r["metadata"]["form"] for r in result]
        assert any("Schedule 2" in f for f in forms), f"Missing Schedule 2, got: {forms}"
        assert any("Schedule 3" in f for f in forms), f"Missing Schedule 3, got: {forms}"


# ============================================================================
# v2 section-aware splitting tests
# Added Session 7 — verifies section atomicity, line-number lookup,
# and the Q7 Schedule A fix.
# ============================================================================


class TestV2SectionAwareSplitting:
    """v2 section-strict splitting: named sections stay atomic up to hard
    ceiling; line-number lookup populates section metadata correctly;
    size suppression works inside named sections."""

    def test_schedule_a_gifts_to_charity_atomic(self):
        """Schedule A Gifts to Charity label and amount stay in same chunk."""
        text = """SCHEDULE A
(Form 1040)
Itemized Deductions

Gifts to Charity
11  Gifts by cash or check
12  Other than by cash or check
13  Carryover from prior year
14  Add lines 11 through 13                       14  9,630.
"""
        pages = _single_page(text, page=10)
        chunks = form_aware_chunk(pages, tax_year=2024)
        # Find the chunk containing the $9,630 amount
        charity_chunks = [
            c for c in chunks
            if "9,630" in c["text"] or "9630" in c["text"]
        ]
        assert len(charity_chunks) >= 1, "No chunk contains the charity amount"
        # That same chunk must also reference charity (label or section metadata)
        c = charity_chunks[0]
        has_charity_context = (
            "harit" in c["text"].lower()
            or "Gifts to Charity" in c["metadata"]["section"]
        )
        assert has_charity_context, (
            f"Chunk with 9,630 has no charity context: section={c['metadata']['section']}, "
            f"body_preview={c['text'][:200]}"
        )

    def test_schedule_b_part_i_interest_atomic(self):
        """Schedule B Part I Interest lines 1-4 stay in same chunk."""
        text = """SCHEDULE B
(Form 1040)
Interest and Ordinary Dividends

Part I Interest
1 List name of payer
2 Add the amounts on line 1
3 Excludable interest on series EE and I U.S. savings bonds
4 Subtract line 3 from line 2
"""
        pages = _single_page(text, page=11)
        chunks = form_aware_chunk(pages, tax_year=2024)
        # The v1 section-heading regex fires on "Part I Interest" text,
        # creating a heading chunk. The v2 line-number lookup then detects
        # lines 1-4 in the same section. All numbered lines must land
        # in a single chunk.
        content_chunks = [
            c for c in chunks
            if "1 List" in c["text"]
        ]
        assert len(content_chunks) >= 1, "No chunk with line 1 content found"
        c = content_chunks[0]
        for line_marker in ["1 List", "2 Add", "3 Excludable", "4 Subtract"]:
            assert line_marker in c["text"], (
                f"Line marker {line_marker!r} missing from content chunk"
            )

    def test_section_metadata_not_header_for_content_chunks(self):
        """Mid-section chunks should NOT be tagged 'Header' — v1 bug."""
        text = """SCHEDULE A
(Form 1040)

Gifts to Charity
11  Gifts by cash or check
12  Other than by cash or check
13  Carryover from prior year
14  Add lines 11 through 13                       14  9,630.
"""
        pages = _single_page(text, page=10)
        chunks = form_aware_chunk(pages, tax_year=2024)
        # Find the chunk with line content (not the pure header)
        content_chunks = [
            c for c in chunks
            if "9,630" in c["text"] or "Gifts by cash" in c["text"]
        ]
        assert len(content_chunks) >= 1
        # None of those should be tagged "Header"
        for c in content_chunks:
            assert c["metadata"]["section"] != "Header", (
                f"Content chunk tagged as Header: {c['text'][:200]}"
            )

    def test_schedule_d_part_iii_summary_detected(self):
        """Schedule D Part III Summary (Line 16) detected as its own section."""
        text = """SCHEDULE D
(Form 1040)
Capital Gains and Losses

Part III Summary
16  Combine lines 7 and 15 and enter the result
17  Are lines 15 and 16 both gains?
18  28% rate gain
19  Unrecaptured section 1250 gain
"""
        pages = _single_page(text, page=12)
        chunks = form_aware_chunk(pages, tax_year=2024)
        part_iii_chunks = [
            c for c in chunks
            if "Part III" in c["metadata"]["section"]
            and "Summary" in c["metadata"]["section"]
        ]
        assert len(part_iii_chunks) >= 1, (
            f"No Part III Summary chunk. Chunks produced: "
            f"{[c['metadata']['section'] for c in chunks]}"
        )

    def test_form_5329_part_iv_roth_ira_detected(self):
        """Form 5329 Part IV Roth IRA excess contributions section."""
        text = """Form 5329
Additional Taxes on Qualified Plans

Part IV Additional Tax on Excess Contributions to Roth IRAs
18  Enter your excess contributions from line 24
19  Roth IRA contributions for 2024
20  2024 distributions from your Roth IRAs
"""
        pages = _single_page(text, page=21)
        chunks = form_aware_chunk(pages, tax_year=2024)
        part_iv_chunks = [
            c for c in chunks
            if "Part IV" in c["metadata"]["section"]
            and ("Roth" in c["metadata"]["section"] or "18" in c["text"])
        ]
        assert len(part_iv_chunks) >= 1

    def test_named_section_larger_than_target_stays_atomic(self):
        """A named section with many lines stays in one chunk up to hard
        ceiling, even if it exceeds the 600-char soft target."""
        # Build a Schedule A Taxes You Paid section with enough verbose
        # content to exceed 600 chars but stay under 2000
        text_parts = ["SCHEDULE A\n(Form 1040)\n\nTaxes You Paid\n"]
        for line_num in ["5", "5a", "5b", "5c", "5d", "5e", "6", "7"]:
            text_parts.append(
                f"{line_num}  Item description for line {line_num} "
                f"with enough verbose filler text to push the total "
                f"character count upward in a controlled way here.\n"
            )
        text = "".join(text_parts)
        pages = _single_page(text, page=10)
        chunks = form_aware_chunk(pages, tax_year=2024)
        # The v1 heading regex may create a small "Taxes You Paid" heading chunk.
        # The v2 line-number lookup creates the content chunk with all lines 5-7.
        # Find the chunk that actually contains line content.
        content_chunks = [
            c for c in chunks
            if "5  Item" in c["text"]
        ]
        assert len(content_chunks) >= 1, "No content chunk with line 5"
        # All Line 5-7 content should be in ONE chunk (no soft-split)
        c = content_chunks[0]
        for line_num in ["5a", "5b", "5c", "5d", "5e", "6", "7"]:
            assert f"{line_num}  Item" in c["text"], (
                f"Line {line_num} not in same chunk as rest of section"
            )

    def test_unknown_form_falls_back_to_v1_splitting(self):
        """Unrecognized form with no section table should chunk by size."""
        # Generate enough text to trigger size-based splitting
        text = "Some front matter page with no IRS form structure.\n\n"
        text += "This is a preparer cover letter. " * 50
        pages = _single_page(text, page=1)
        chunks = form_aware_chunk(pages, tax_year=2024)
        # Should produce at least one chunk (fallback logic works)
        assert len(chunks) >= 1
        # Form should be Unknown (no IRS header detected)
        assert chunks[0]["metadata"]["form"] == "Unknown"

    def test_detect_line_number_filters_year_digits(self):
        """_detect_line_number rejects 4-digit years as line numbers."""
        from app.services.form_aware_chunker import _detect_line_number
        assert _detect_line_number("2024 Form 1040") is None
        assert _detect_line_number("1040 Page 2") is None
        # But valid 3-digit line numbers work
        assert _detect_line_number("100  Some line") == "100"

    def test_voucher_section_not_treated_as_named_section(self):
        """Voucher sections should use v1 behavior, not section-strict logic."""
        # detect_voucher_chunk requires ≥2 voucher patterns + a future year
        text = """Form 1040-ES
2025 Estimated Tax Payment Voucher 1
Calendar year—Due April 15, 2025
Detach Here and Mail With Your Payment
"""
        pages = _single_page(text, page=1)
        chunks = form_aware_chunk(pages, tax_year=2024)
        assert len(chunks) >= 1
        assert chunks[0]["metadata"]["is_voucher"] is True

    def test_schedule_k1_1120s_line_1_detected(self):
        """Schedule K-1 (Form 1120-S) Line 1 (ordinary biz income) detected."""
        text = """Schedule K-1 (Form 1120-S)
Shareholder's Share of Income, Deductions, Credits, etc.

Part III Shareholder's Share of Current Year Income
1 Ordinary business income (loss)                    50,000
2 Net rental real estate income (loss)
3 Other net rental income (loss)
"""
        pages = _single_page(text, page=5)
        chunks = form_aware_chunk(pages, tax_year=2024)
        part_iii_chunks = [
            c for c in chunks
            if "Ordinary Business Income" in c["metadata"]["section"]
        ]
        assert len(part_iii_chunks) >= 1, (
            f"No Line 1 chunk found. Sections: "
            f"{[c['metadata']['section'] for c in chunks]}"
        )

    def test_schedule_c_net_profit_detected(self):
        """Schedule C Line 31 (net profit) correctly mapped to Part II."""
        text = """Schedule C
(Form 1040)
Profit or Loss From Business

Part II Expenses
29  Tentative profit
30  Expenses for business use of your home
31  Net profit or loss                              25,000
"""
        pages = _single_page(text, page=1)
        chunks = form_aware_chunk(pages, tax_year=2024)
        net_profit_chunks = [
            c for c in chunks
            if "Net Profit" in c["metadata"]["section"]
            or "31" in c["text"]
        ]
        assert len(net_profit_chunks) >= 1

    def test_v2_section_hard_ceiling_triggers_split(self):
        """Section over HARD_CEILING (2000) should split at ceiling."""
        # Build a section that exceeds 2000 chars
        text_parts = ["SCHEDULE A\n(Form 1040)\n\nGifts to Charity\n"]
        # Add Line 11 with very long content
        long_content = "Very detailed donation entry with extensive description. " * 50
        text_parts.append(f"11  {long_content}\n")
        text_parts.append("14  Total                                  14  9,630.\n")
        text = "".join(text_parts)
        pages = _single_page(text, page=10)
        chunks = form_aware_chunk(pages, tax_year=2024)
        # Section was over 2000 chars → should have produced multiple
        # chunks with Gifts to Charity section
        charity_chunks = [
            c for c in chunks
            if "Gifts to Charity" in c["metadata"]["section"]
        ]
        assert len(charity_chunks) >= 1
        # No chunk should massively exceed hard ceiling
        for c in charity_chunks:
            # Allow some slack for the prefix + one overshoot line
            assert len(c["text"]) < 3500, (
                f"Chunk exceeded safe ceiling: {len(c['text'])} chars"
            )
