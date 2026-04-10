"""Tests for extract_tax_year_from_filename."""

from app.services.rag_service import extract_tax_year_from_filename


def test_plain_year_in_filename():
    assert extract_tax_year_from_filename("2024 Tax Return.pdf") == 2024


def test_year_no_spaces():
    assert extract_tax_year_from_filename("TaxReturn2024.pdf") == 2024


def test_year_with_underscores():
    assert extract_tax_year_from_filename("michael_2024_1040.pdf") == 2024


def test_multiple_years_picks_last():
    assert extract_tax_year_from_filename("2023_amended_2024.pdf") == 2024


def test_no_year():
    assert extract_tax_year_from_filename("meeting_notes.pdf") is None


def test_empty_string():
    assert extract_tax_year_from_filename("") is None


def test_none_input():
    assert extract_tax_year_from_filename(None) is None


def test_year_at_end():
    assert extract_tax_year_from_filename("K1-2024.pdf") == 2024


def test_non_tax_year_ignored():
    """Years outside the 20xx range are not matched."""
    assert extract_tax_year_from_filename("report_1999.pdf") is None
