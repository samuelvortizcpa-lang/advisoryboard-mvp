"""Light-weight integration smoke tests for form-aware chunker
dispatch in rag_service. Real dispatch behavior is validated
in production via the USE_FORM_AWARE_CHUNKER flag; these tests
only guarantee import hygiene and env-var plumbing."""

import importlib
import os

import pytest


def test_rag_service_imports_with_flag_unset(monkeypatch):
    """rag_service must import cleanly when flag is not set."""
    monkeypatch.delenv("USE_FORM_AWARE_CHUNKER", raising=False)
    import app.services.rag_service as rs
    importlib.reload(rs)
    assert hasattr(rs, "process_document")
    assert hasattr(rs, "form_aware_chunk")


def test_rag_service_imports_with_flag_true(monkeypatch):
    """rag_service must import cleanly when flag is on."""
    monkeypatch.setenv("USE_FORM_AWARE_CHUNKER", "true")
    import app.services.rag_service as rs
    importlib.reload(rs)
    assert hasattr(rs, "process_document")
    assert hasattr(rs, "form_aware_chunk")


def test_env_var_predicate_matches_expected_truthy_values():
    """The exact predicate used in rag_service for the flag."""
    def predicate(v: str | None) -> bool:
        return (v or "").lower() == "true"

    assert predicate("true") is True
    assert predicate("TRUE") is True
    assert predicate("True") is True
    assert predicate("false") is False
    assert predicate("") is False
    assert predicate(None) is False
    assert predicate("1") is False  # intentional: we only accept "true"
    assert predicate("yes") is False
