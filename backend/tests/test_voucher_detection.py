"""Tests for 1040-ES voucher chunk detection."""

from app.services.chunking import detect_voucher_chunk


def test_real_voucher_chunk_flagged():
    """A real 1040-ES voucher chunk with a future year should be flagged."""
    chunk = (
        "[Page 2]\n"
        "Form 1040-ES\n"
        "Department of the Treasury\n"
        "Internal Revenue Service\n\n"
        "2025 Estimated Tax Payment Voucher 1\n"
        "Calendar year—Due April 15, 2025\n\n"
        "Amount of estimated tax you are paying by check\n"
        "or money order: $12,500\n\n"
        "Michael Tjahjadi\n"
        "123 Main Street\n"
    )
    result = detect_voucher_chunk(chunk, return_tax_year=2024)
    assert result["is_voucher"] is True
    assert result["voucher_type"] == "1040-ES"
    assert result["voucher_year"] == 2025


def test_1040_page_mentioning_estimated_tax_not_flagged():
    """A page from the actual 1040 that mentions 'estimated tax' in passing
    should NOT be flagged — no future year present."""
    chunk = (
        "[Page 6]\n"
        "Form 1040 (2024)\n"
        "Line 26: Estimated tax payments and amount applied from 2023 return\n"
        "Amount: $15,000\n\n"
        "Line 33: Total payments\n"
        "Amount: $55,000\n"
    )
    result = detect_voucher_chunk(chunk, return_tax_year=2024)
    assert result["is_voucher"] is False


def test_form_1040es_without_future_year_not_flagged():
    """A chunk with 'Form 1040-ES' but no future year should not be flagged."""
    chunk = (
        "For more information about Form 1040-ES, see the instructions.\n"
        "You may need to adjust your withholding.\n"
    )
    result = detect_voucher_chunk(chunk, return_tax_year=2024)
    assert result["is_voucher"] is False


def test_schedule_a_not_flagged():
    """A Schedule A chunk with no voucher language should not be flagged."""
    chunk = (
        "[Page 10]\n"
        "Schedule A (Form 1040)\n"
        "Itemized Deductions\n\n"
        "Line 5: State and local taxes: $10,000\n"
        "Line 14: Charitable contributions: $9,630\n"
    )
    result = detect_voucher_chunk(chunk)
    assert result["is_voucher"] is False
    assert result["voucher_type"] is None
    assert result["voucher_year"] is None


def test_voucher_without_return_year():
    """Without a known return_tax_year, any year >= 2025 should trigger detection."""
    chunk = (
        "Payment Voucher\n"
        "Estimated tax for tax year 2026\n"
        "Amount: $5,000\n"
    )
    result = detect_voucher_chunk(chunk)
    assert result["is_voucher"] is True
    assert result["voucher_year"] == 2026


def test_voucher_picks_max_future_year():
    """When multiple future years appear, pick the max."""
    chunk = (
        "Form 1040-ES\n"
        "2025 Estimated Tax Payment Voucher\n"
        "Due dates: April 2025, June 2025, September 2025, January 2026\n"
    )
    result = detect_voucher_chunk(chunk, return_tax_year=2024)
    assert result["is_voucher"] is True
    assert result["voucher_year"] == 2026
