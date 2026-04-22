"""
Unit tests for extract_with_strategy dispatcher.

All tests mock underlying extractors and page counting — no real
DocAI calls, no real GCS, no real PDFs. Verifies the routing
decision tree and feature-flag handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services import document_ai_service
from app.services.document_ai_service import (
    DocAITooLarge,
    extract_with_strategy,
)


# --- Fixtures ---

@pytest.fixture
def fake_bytes() -> bytes:
    # Content is irrelevant; all reads are mocked.
    return b"%PDF-1.4 fake"


@pytest.fixture
def mock_available(monkeypatch):
    """is_available() returns True by default for tests below."""
    monkeypatch.setattr(document_ai_service, "is_available", lambda: True)


@pytest.fixture
def mock_online_extractors(monkeypatch):
    """
    Stub both online extractors. Returns a dict with references so
    tests can assert on call args.
    """
    fp_mock = MagicMock(return_value={"text": "form_parser_output", "pages": []})
    ocr_mock = MagicMock(return_value={"text": "ocr_output", "pages": []})
    monkeypatch.setattr(document_ai_service, "extract_with_form_parser", fp_mock)
    monkeypatch.setattr(document_ai_service, "extract_with_ocr", ocr_mock)
    return {"form_parser": fp_mock, "ocr": ocr_mock}


# --- Tests: is_available gating ---

def test_returns_none_when_docai_unavailable(monkeypatch, fake_bytes):
    monkeypatch.setattr(document_ai_service, "is_available", lambda: False)
    assert extract_with_strategy(fake_bytes, "tax_return") is None


# --- Tests: page-count failure ---

def test_returns_none_when_page_count_unknown(
    monkeypatch, fake_bytes, mock_available
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: None)
    assert extract_with_strategy(fake_bytes, "tax_return") is None


# --- Tests: online tier routing ---

def test_small_financial_doc_routes_to_form_parser_with_imageless(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 10)
    result = extract_with_strategy(fake_bytes, "tax_return")
    assert result == {"text": "form_parser_output", "pages": []}
    mock_online_extractors["form_parser"].assert_called_once_with(
        fake_bytes, imageless_mode=True
    )
    mock_online_extractors["ocr"].assert_not_called()


def test_small_nonfinancial_doc_routes_to_ocr_with_imageless(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 10)
    result = extract_with_strategy(fake_bytes, "transcript")
    assert result == {"text": "ocr_output", "pages": []}
    mock_online_extractors["ocr"].assert_called_once_with(
        fake_bytes, imageless_mode=True
    )
    mock_online_extractors["form_parser"].assert_not_called()


def test_none_document_type_routes_to_ocr(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 5)
    extract_with_strategy(fake_bytes, None)
    mock_online_extractors["ocr"].assert_called_once()
    mock_online_extractors["form_parser"].assert_not_called()


def test_case_insensitive_financial_type(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 5)
    extract_with_strategy(fake_bytes, "Tax_Return")
    mock_online_extractors["form_parser"].assert_called_once()


def test_online_tier_boundary_30_pages_uses_online(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    """30 pages should still route online (imageless_mode extends to 30)."""
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 30)
    extract_with_strategy(fake_bytes, "tax_return")
    mock_online_extractors["form_parser"].assert_called_once_with(
        fake_bytes, imageless_mode=True
    )


# --- Tests: batch tier + feature flag ---

def test_batch_tier_returns_none_when_flag_off(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 50)
    monkeypatch.setattr(document_ai_service, "USE_DOCAI_BATCH", False)
    result = extract_with_strategy(fake_bytes, "tax_return")
    assert result is None
    mock_online_extractors["form_parser"].assert_not_called()
    mock_online_extractors["ocr"].assert_not_called()


def test_batch_tier_returns_none_when_gcs_env_missing(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 50)
    monkeypatch.setattr(document_ai_service, "USE_DOCAI_BATCH", True)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("DOCAI_OCR_PROCESSOR_ID", raising=False)
    result = extract_with_strategy(fake_bytes, "tax_return")
    assert result is None


def test_batch_tier_calls_batch_extractor_with_flag_on(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 50)
    monkeypatch.setattr(document_ai_service, "USE_DOCAI_BATCH", True)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("DOCAI_OCR_PROCESSOR_ID", "test-ocr-id")
    monkeypatch.setenv("DOCAI_GCS_BUCKET", "test-bucket")

    fake_batch_result = {"text": "batch_output", "pages": [{"page_number": 1, "text": "p1"}]}
    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = fake_batch_result
    fake_extractor_cls = MagicMock(return_value=fake_extractor)

    # Patch at import site: extract_with_strategy imports BatchExtractor locally
    import app.services.batch_extractor as batch_mod
    monkeypatch.setattr(batch_mod, "BatchExtractor", fake_extractor_cls)

    result = extract_with_strategy(fake_bytes, "tax_return")

    assert result == fake_batch_result
    fake_extractor_cls.assert_called_once()
    fake_extractor.extract.assert_called_once()
    call_kwargs = fake_extractor.extract.call_args.kwargs
    assert call_kwargs["file_bytes"] == fake_bytes
    assert "processors/test-ocr-id" in call_kwargs["processor_name"]
    assert len(call_kwargs["document_id"]) == 32  # uuid4 hex


def test_batch_tier_catches_DocAIBatchError_and_returns_none(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 50)
    monkeypatch.setattr(document_ai_service, "USE_DOCAI_BATCH", True)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("DOCAI_OCR_PROCESSOR_ID", "test-ocr-id")
    monkeypatch.setenv("DOCAI_GCS_BUCKET", "test-bucket")

    import app.services.batch_extractor as batch_mod
    fake_extractor = MagicMock()
    fake_extractor.extract.side_effect = batch_mod.DocAIBatchFailed("mock failure")
    fake_extractor_cls = MagicMock(return_value=fake_extractor)
    monkeypatch.setattr(batch_mod, "BatchExtractor", fake_extractor_cls)

    result = extract_with_strategy(fake_bytes, "tax_return")
    assert result is None  # caught, not raised


# --- Tests: splitting tier (>200 pages) ---

def test_large_doc_raises_doc_ai_too_large(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 250)
    with pytest.raises(DocAITooLarge) as exc_info:
        extract_with_strategy(fake_bytes, "tax_return")
    assert "250 pages" in str(exc_info.value)
    assert "200" in str(exc_info.value)


def test_batch_tier_boundary_200_pages_still_batch(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    """200 pages is the upper boundary of batch — still routed there, not raised."""
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 200)
    monkeypatch.setattr(document_ai_service, "USE_DOCAI_BATCH", False)
    # Flag off → returns None rather than raising
    result = extract_with_strategy(fake_bytes, "tax_return")
    assert result is None


def test_splitting_tier_boundary_201_pages_raises(
    monkeypatch, fake_bytes, mock_available, mock_online_extractors
):
    """201 pages is above batch cap — DocAITooLarge regardless of flag."""
    monkeypatch.setattr(document_ai_service, "_count_pdf_pages", lambda _: 201)
    monkeypatch.setattr(document_ai_service, "USE_DOCAI_BATCH", True)
    with pytest.raises(DocAITooLarge):
        extract_with_strategy(fake_bytes, "tax_return")
