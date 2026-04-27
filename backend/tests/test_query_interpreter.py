"""Tests for query_interpreter module and expand_query interpretation merge."""

import asyncio

import pytest

from app.services.query_interpreter import InterpretationResult, interpret_query_llm
from app.services.tax_terms import expand_query


# ── Group A: expand_query merge logic (sync) ─────────────────────────


def test_expand_query_no_interpretation_byte_identical_to_baseline():
    """The no-kwarg path must return the locked dictionary values.

    This is the load-bearing safety property for Session 19's
    flag-off rollout. Hardcoded expected values so dictionary
    changes that drop these entries break this test loudly.
    """
    terms, forms = expand_query("shareholder distribution")
    assert terms == [
        "schedule k line 16d",
        "schedule m-2 line 7",
        "accumulated adjustments account",
    ]
    assert forms == ["schedule k", "schedule m-2"]


def test_expand_query_with_none_interpretation_byte_identical_to_no_kwarg():
    """Explicit None and omitted kwarg must be indistinguishable."""
    result_omit = expand_query("shareholder distribution")
    result_none = expand_query("shareholder distribution", interpretation=None)
    assert result_omit == result_none


def test_expand_query_with_interpretation_unions_signals():
    interp = InterpretationResult(
        forms=["1120-S", "Schedule K"],
        keywords=["ordinary business income"],
        intent="factual_lookup",
        confidence=0.85,
    )
    terms_base, forms_base = expand_query("shareholder distribution")
    terms_merged, forms_merged = expand_query(
        "shareholder distribution", interpretation=interp
    )

    # Superset property
    assert set(t.lower() for t in terms_base).issubset(
        set(t.lower() for t in terms_merged)
    )
    assert set(f.lower() for f in forms_base).issubset(
        set(f.lower() for f in forms_merged)
    )

    # LLM-derived signals present
    assert "ordinary business income" in terms_merged
    assert "1120-S" in forms_merged

    # Dedup note: the dictionary returns 'schedule k' (lowercase)
    # and the interpretation provides 'Schedule K' (titlecase).
    # The dedup is case-insensitive (compares .lower()), so only
    # one survives — the dictionary's version wins because it
    # appears first. If Session 19 LLM returns lowercase, this
    # is moot; documenting here for awareness.
    schedule_k_hits = [f for f in forms_merged if f.lower() == "schedule k"]
    assert len(schedule_k_hits) == 1


def test_expand_query_dedup_within_interpretation_only():
    """Interpretation-only duplicates must be deduped."""
    interp = InterpretationResult(
        forms=["1120-S", "1120-S", "Schedule K"],
        keywords=["ordinary business income", "ordinary business income"],
    )
    # Query that triggers NO dictionary entries
    terms, forms = expand_query("what color is the sky", interpretation=interp)

    assert terms == ["ordinary business income"]
    assert forms == ["1120-S", "Schedule K"]


def test_expand_query_with_empty_interpretation_equivalent_to_none():
    """An empty InterpretationResult (all defaults) adds nothing.

    Callers who want to skip merging should pass None (canonical
    skip signal), but empty-interpretation must also be safe.
    """
    interp_empty = InterpretationResult()
    result_none = expand_query("shareholder distribution")
    result_empty = expand_query("shareholder distribution", interpretation=interp_empty)
    assert result_none == result_empty


def test_expand_query_keyword_only_kwarg():
    """The bare * in the signature forbids positional misuse."""
    with pytest.raises(TypeError):
        expand_query("question", InterpretationResult())


# ── Group B: interpret_query_llm stub (async) ────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "What was Tracy Chen DO, Inc's ordinary business income in 2024?",
        "What is my AGI on Form 1040?",
        "xyzzy nonsense query",
        "",
    ],
)
async def test_interpret_query_llm_stub_returns_none_for_any_question(question):
    """Stub always returns None (Session 18). Session 19 replaces with real call."""
    result = await interpret_query_llm(question)
    assert result is None


# ── Group C: InterpretationResult shape (sync) ───────────────────────


def test_interpretation_result_default_construction():
    r = InterpretationResult()
    assert r.forms == []
    assert r.line_numbers == []
    assert r.keywords == []
    assert r.intent == "unknown"
    assert r.confidence == 0.0
    assert r.reasoning is None
    assert r.schema_version == "v1"


def test_interpretation_result_is_frozen():
    r = InterpretationResult(forms=["1040"])
    with pytest.raises((AttributeError, TypeError)):
        r.forms = ["changed"]


def test_interpretation_result_intent_literal_validation():
    """Literal type is NOT runtime-enforced in Python. This test
    documents that the canonical intent values construct cleanly.
    Invalid values also construct (Literal is advisory); runtime
    validation may be added in Session 19.
    """
    canonical_intents = [
        "factual_lookup",
        "enumeration",
        "synthesis",
        "advisory",
        "unknown",
    ]
    for intent in canonical_intents:
        r = InterpretationResult(intent=intent)
        assert r.intent == intent
