"""Tests for query_interpreter module and expand_query interpretation merge."""

import asyncio
import logging
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.query_interpreter import (
    InterpretationResult,
    interpret_query_llm,
    _cache_key,
    _cache_get,
    _cache_set,
    _cache_clear,
    _CACHE_MISS,
    _CACHE_MAXSIZE,
    CONFIDENCE_THRESHOLD,
)
from app.services.tax_terms import expand_query


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_query_interpreter_state(monkeypatch):
    """Reset all module-level state between tests to prevent leakage."""
    from app.services import query_interpreter as qi
    qi._cache_clear()
    qi._client = None
    qi._missing_key_alerted = False
    qi._auth_failure_alerted = False
    monkeypatch.delenv("USE_LLM_QUERY_INTERPRETATION", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield


@pytest.fixture
def mock_anthropic_client(monkeypatch):
    """Install a mocked AsyncAnthropic client with flag on."""
    from app.services import query_interpreter as qi
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    monkeypatch.setenv("USE_LLM_QUERY_INTERPRETATION", "true")
    create_mock = AsyncMock()
    client = SimpleNamespace(messages=SimpleNamespace(create=create_mock))
    qi._client = client
    return create_mock


@pytest.fixture
def captured_logs():
    """Capture log records directly on the module logger (resilient to root config)."""
    records = []

    class _Handler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Handler()
    handler.setLevel(logging.DEBUG)
    qi_logger = logging.getLogger("app.services.query_interpreter")
    old_level = qi_logger.level
    qi_logger.setLevel(logging.DEBUG)
    qi_logger.addHandler(handler)
    yield SimpleNamespace(records=records)
    qi_logger.removeHandler(handler)
    qi_logger.setLevel(old_level)


@pytest.fixture
def captured_sentry(monkeypatch):
    from app.services import query_interpreter as qi
    msgs = []
    excs = []
    monkeypatch.setattr(qi.sentry_sdk, "capture_message",
                        lambda msg, level=None, **kw: msgs.append((msg, level)))
    monkeypatch.setattr(qi.sentry_sdk, "capture_exception",
                        lambda *a, **kw: excs.append(a))

    @contextmanager
    def fake_push_scope():
        yield SimpleNamespace(set_extra=lambda *a, **kw: None)
    monkeypatch.setattr(qi.sentry_sdk, "push_scope", fake_push_scope)
    return SimpleNamespace(messages=msgs, exceptions=excs)


# ── Helpers ───────────────────────────────────────────────────────────


def _make_tool_use_response(payload, tool_name="record_interpretation"):
    block = SimpleNamespace(type="tool_use", name=tool_name, input=payload)
    return SimpleNamespace(content=[block])


def _valid_payload(**overrides):
    base = {
        "forms": ["1040"],
        "line_numbers": ["11"],
        "keywords": ["adjusted gross income"],
        "intent": "factual_lookup",
        "confidence": 0.9,
        "reasoning": "User is asking about a specific 1040 line.",
    }
    base.update(overrides)
    return base


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


# ── Group B: flag-off behavior (async) ────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "What was Tracy Chen DO, Inc's ordinary business income in 2024?",
        "What is my AGI on Form 1040?",
        "xyzzy nonsense query",
        "",
    ],
)
async def test_interpret_query_llm_returns_none_when_flag_off(question):
    """Flag-off path returns None for any question."""
    result = await interpret_query_llm(question)
    assert result is None


async def test_flag_off_returns_none_no_sdk_call_no_log(
    mock_anthropic_client, captured_logs, captured_sentry, monkeypatch,
):
    """Flag off: no SDK call, no log line, no Sentry call."""
    monkeypatch.setenv("USE_LLM_QUERY_INTERPRETATION", "false")
    result = await interpret_query_llm("test question")
    assert result is None
    mock_anthropic_client.assert_not_called()
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert len(qi_records) == 0
    assert len(captured_sentry.messages) == 0


async def test_flag_off_skips_cache_entirely(mock_anthropic_client, monkeypatch):
    """Flag off does not consult the cache even if populated."""
    monkeypatch.setenv("USE_LLM_QUERY_INTERPRETATION", "false")
    cached_result = InterpretationResult(forms=["1040"], confidence=0.9, reasoning="x")
    _cache_set(_cache_key("test question"), cached_result)
    result = await interpret_query_llm("test question")
    assert result is None  # flag gate returns None before cache check
    mock_anthropic_client.assert_not_called()


# ── Group C: missing API key ─────────────────────────────────────────


async def test_no_api_key_returns_none_no_log_one_sentry(
    monkeypatch, captured_logs, captured_sentry,
):
    """Missing API key: zero logs, one Sentry alert."""
    monkeypatch.setenv("USE_LLM_QUERY_INTERPRETATION", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.services import query_interpreter as qi
    qi._client = None  # force re-check

    result = await interpret_query_llm("q1")
    assert result is None
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert len(qi_records) == 0
    assert len(captured_sentry.messages) == 1
    assert captured_sentry.messages[0][1] == "error"


async def test_no_api_key_alert_deduped_across_calls(
    monkeypatch, captured_sentry,
):
    """Missing API key Sentry alert fires once, not per call."""
    monkeypatch.setenv("USE_LLM_QUERY_INTERPRETATION", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.services import query_interpreter as qi
    qi._client = None

    for q in ("q1", "q2", "q3"):
        await interpret_query_llm(q)
    assert len(captured_sentry.messages) == 1


# ── Group D: cache hits ──────────────────────────────────────────────


async def test_positive_cache_hit_returns_cached_result_logs_from_cache_true(
    mock_anthropic_client, captured_logs,
):
    cached = InterpretationResult(
        forms=["1040"], keywords=["agi"], intent="factual_lookup",
        confidence=0.9, reasoning="cached",
    )
    _cache_set(_cache_key("cached q"), cached)
    result = await interpret_query_llm("cached q")
    assert result is cached
    mock_anthropic_client.assert_not_called()
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert len(qi_records) == 1
    assert qi_records[0].from_cache is True
    assert qi_records[0].success is True


async def test_negative_cache_hit_returns_none_logs_from_cache_true_success_false(
    mock_anthropic_client, captured_logs,
):
    _cache_set(_cache_key("neg q"), None)
    result = await interpret_query_llm("neg q")
    assert result is None
    mock_anthropic_client.assert_not_called()
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert len(qi_records) == 1
    assert qi_records[0].from_cache is True
    assert qi_records[0].success is False
    assert qi_records[0].fallback_triggered is True


# ── Group E: successful LLM call ─────────────────────────────────────


async def test_success_returns_interpretation_result_logs_success_true(
    mock_anthropic_client, captured_logs,
):
    payload = _valid_payload()
    mock_anthropic_client.return_value = _make_tool_use_response(payload)
    result = await interpret_query_llm("what is my AGI")
    assert isinstance(result, InterpretationResult)
    assert result.forms == ["1040"]
    assert result.keywords == ["adjusted gross income"]
    assert result.intent == "factual_lookup"
    assert result.confidence == 0.9
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert len(qi_records) == 1
    assert qi_records[0].success is True
    assert qi_records[0].from_cache is False
    assert qi_records[0].forms_count == 1
    assert qi_records[0].keywords_count == 1


async def test_success_caches_result_subsequent_call_is_cache_hit(
    mock_anthropic_client, captured_logs,
):
    mock_anthropic_client.return_value = _make_tool_use_response(_valid_payload())
    r1 = await interpret_query_llm("same question")
    r2 = await interpret_query_llm("same question")
    assert r1 is not None
    assert r2 is r1  # identity — came from cache
    assert mock_anthropic_client.call_count == 1
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert len(qi_records) == 2
    assert qi_records[0].from_cache is False
    assert qi_records[1].from_cache is True


async def test_success_with_different_question_does_not_share_cache(
    mock_anthropic_client,
):
    mock_anthropic_client.return_value = _make_tool_use_response(_valid_payload())
    await interpret_query_llm("question A")
    await interpret_query_llm("question B")
    assert mock_anthropic_client.call_count == 2


# ── Group F: cache key behavior ──────────────────────────────────────


def test_cache_key_normalization():
    assert _cache_key("Foo") == _cache_key("  foo  ")
    assert _cache_key("Foo") != _cache_key("Bar")


def test_cache_key_includes_prompt_version_and_model(monkeypatch):
    from app.services import query_interpreter as qi
    k1 = _cache_key("test")
    monkeypatch.setattr(qi, "PROMPT_VERSION", "v2")
    k2 = _cache_key("test")
    assert k1 != k2
    monkeypatch.setattr(qi, "PROMPT_VERSION", "v1")
    monkeypatch.setattr(qi, "MODEL_ID", "claude-test-model")
    k3 = _cache_key("test")
    assert k1 != k3


def test_cache_eviction_at_maxsize():
    for i in range(_CACHE_MAXSIZE + 1):
        _cache_set(_cache_key(f"q_{i}"), None)
    assert _cache_get(_cache_key("q_0")) is _CACHE_MISS  # evicted
    assert _cache_get(_cache_key(f"q_{_CACHE_MAXSIZE}")) is None  # present
    from app.services.query_interpreter import _cache
    assert len(_cache) == _CACHE_MAXSIZE


# ── Group G: failure modes ───────────────────────────────────────────


async def test_timeout_returns_none_caches_none_logs_fallback(
    mock_anthropic_client, captured_logs,
):
    mock_anthropic_client.side_effect = asyncio.TimeoutError()
    r1 = await interpret_query_llm("timeout q")
    assert r1 is None
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert qi_records[0].fallback_triggered is True
    assert qi_records[0].from_cache is False
    # Second call hits negative cache
    r2 = await interpret_query_llm("timeout q")
    assert r2 is None
    assert mock_anthropic_client.call_count == 1


async def test_api_error_returns_none_caches_none_logs_fallback(
    mock_anthropic_client, captured_logs,
):
    import anthropic
    mock_anthropic_client.side_effect = anthropic.APIError(
        message="server error", request=SimpleNamespace(method="POST", url="test"),
        body=None,
    )
    result = await interpret_query_llm("api error q")
    assert result is None
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert qi_records[0].fallback_triggered is True


async def test_authentication_error_returns_none_logs_fires_one_sentry(
    mock_anthropic_client, captured_logs, captured_sentry,
):
    import anthropic
    mock_anthropic_client.side_effect = anthropic.AuthenticationError(
        message="invalid key",
        response=SimpleNamespace(status_code=401, headers={}, text="",
                                 json=lambda: {}, content=b"", request=None),
        body=None,
    )
    result = await interpret_query_llm("auth fail q")
    assert result is None
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert qi_records[0].fallback_triggered is True
    assert len(captured_sentry.messages) == 1
    assert captured_sentry.messages[0][1] == "error"


async def test_authentication_error_dedup_across_calls(
    mock_anthropic_client, captured_sentry,
):
    import anthropic
    mock_anthropic_client.side_effect = anthropic.AuthenticationError(
        message="invalid key",
        response=SimpleNamespace(status_code=401, headers={}, text="",
                                 json=lambda: {}, content=b"", request=None),
        body=None,
    )
    for q in ("q1", "q2", "q3"):
        await interpret_query_llm(q)
    assert len(captured_sentry.messages) == 1


async def test_unexpected_exception_returns_none_fires_capture_exception(
    mock_anthropic_client, captured_logs, captured_sentry,
):
    mock_anthropic_client.side_effect = ValueError("boom")
    result = await interpret_query_llm("unexpected q")
    assert result is None
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert qi_records[0].fallback_triggered is True
    assert len(captured_sentry.exceptions) == 1


# ── Group H: tool-use block extraction ───────────────────────────────


async def test_missing_tool_use_block_returns_none_caches_none(
    mock_anthropic_client, captured_logs,
):
    mock_anthropic_client.return_value = SimpleNamespace(content=[])
    result = await interpret_query_llm("empty content q")
    assert result is None
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert qi_records[0].fallback_triggered is True


async def test_wrong_tool_name_returns_none(mock_anthropic_client):
    mock_anthropic_client.return_value = _make_tool_use_response(
        _valid_payload(), tool_name="wrong_name"
    )
    result = await interpret_query_llm("wrong tool q")
    assert result is None


async def test_text_block_only_no_tool_use_returns_none(mock_anthropic_client):
    text_block = SimpleNamespace(type="text", text="I don't know")
    mock_anthropic_client.return_value = SimpleNamespace(content=[text_block])
    result = await interpret_query_llm("text only q")
    assert result is None


# ── Group I: schema validation ───────────────────────────────────────


async def test_schema_missing_required_field_returns_none_fires_sentry(
    mock_anthropic_client, captured_logs, captured_sentry,
):
    payload = _valid_payload()
    del payload["intent"]
    mock_anthropic_client.return_value = _make_tool_use_response(payload)
    result = await interpret_query_llm("bad schema q")
    assert result is None
    assert len(captured_sentry.messages) == 1
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert qi_records[0].fallback_triggered is True


async def test_schema_wrong_type_for_forms_returns_none(mock_anthropic_client):
    mock_anthropic_client.return_value = _make_tool_use_response(
        _valid_payload(forms="not a list")
    )
    result = await interpret_query_llm("bad forms q")
    assert result is None


async def test_schema_invalid_intent_enum_returns_none(mock_anthropic_client):
    mock_anthropic_client.return_value = _make_tool_use_response(
        _valid_payload(intent="guessing")
    )
    result = await interpret_query_llm("bad intent q")
    assert result is None


async def test_schema_confidence_out_of_range_returns_none(mock_anthropic_client):
    mock_anthropic_client.return_value = _make_tool_use_response(
        _valid_payload(confidence=1.5)
    )
    result = await interpret_query_llm("bad confidence q")
    assert result is None


async def test_schema_failure_not_deduped_across_calls(
    mock_anthropic_client, captured_sentry,
):
    """Schema failure Sentry alerts fire per-call (not deduped by design)."""
    for i in range(3):
        payload = _valid_payload()
        del payload["intent"]
        mock_anthropic_client.return_value = _make_tool_use_response(payload)
        await interpret_query_llm(f"bad schema q{i}")
    assert len(captured_sentry.messages) == 3


# ── Group J: confidence threshold ────────────────────────────────────


async def test_low_confidence_returns_none_log_includes_confidence_value(
    mock_anthropic_client, captured_logs,
):
    mock_anthropic_client.return_value = _make_tool_use_response(
        _valid_payload(confidence=0.4)
    )
    result = await interpret_query_llm("low conf q")
    assert result is None
    qi_records = [r for r in captured_logs.records
                  if "query_interpretation" in r.getMessage()]
    assert qi_records[0].confidence == 0.4
    assert qi_records[0].intent == "factual_lookup"


async def test_at_threshold_passes(mock_anthropic_client):
    """Confidence == CONFIDENCE_THRESHOLD passes (check is <, not <=)."""
    mock_anthropic_client.return_value = _make_tool_use_response(
        _valid_payload(confidence=CONFIDENCE_THRESHOLD)
    )
    result = await interpret_query_llm("threshold q")
    assert isinstance(result, InterpretationResult)
    assert result.confidence == CONFIDENCE_THRESHOLD


async def test_just_below_threshold_fails(mock_anthropic_client):
    mock_anthropic_client.return_value = _make_tool_use_response(
        _valid_payload(confidence=CONFIDENCE_THRESHOLD - 0.0001)
    )
    result = await interpret_query_llm("below threshold q")
    assert result is None


# ── Group K: InterpretationResult shape (sync) ───────────────────────


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
