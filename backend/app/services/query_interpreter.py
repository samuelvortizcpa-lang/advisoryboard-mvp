"""
Query interpretation for retrieval-time signal enrichment.

Produces structured interpretation of user queries (forms, line numbers,
keywords, intent) that augments the static TERM_EXPANSIONS dictionary in
tax_terms.py.  The dictionary handles known trigger phrases; this module
handles the open-ended tail — questions about forms, lines, or concepts
the dictionary doesn't cover.

See AdvisoryBoard_QueryInterpretation_Architecture.md (Session 17 design
doc) for the full design.  Session 18 = stub + schema + merge logic.
Session 19 = real Anthropic integration.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal

import anthropic
import sentry_sdk
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InterpretationResult:
    """Structured interpretation of a user query for retrieval signals."""

    # Canonical form names: "1120-S", "Schedule K", "Form 100S", etc.
    # Empty list valid.
    forms: list[str] = field(default_factory=list)

    # Specific line numbers when mentioned/inferable. Empty common.
    line_numbers: list[str] = field(default_factory=list)

    # Canonical concept phrasings: "ordinary business income",
    # "shareholder distribution". Empty list valid.
    keywords: list[str] = field(default_factory=list)

    # Classified query intent.
    intent: Literal[
        "factual_lookup", "enumeration", "synthesis", "advisory", "unknown"
    ] = "unknown"

    # Self-reported confidence, 0.0-1.0.
    confidence: float = 0.0

    # Debugging only, not used in retrieval.
    reasoning: str | None = None

    # Bumped on schema-breaking changes; callers can validate.
    schema_version: str = "v1"


# ── Constants ─────────────────────────────────────────────────────────

MODEL_ID = "claude-haiku-4-5-20251001"
PROMPT_VERSION = "v1"
CONFIDENCE_THRESHOLD = 0.5
# Session 20 Phase 1 probe (N=10, real Haiku 4.5, production prompt+tool):
# p50≈2.3s, max≈4.6s, retry rate 0%. SOFT is the SDK httpx timeout per
# request; HARD is the asyncio.wait_for backstop. Both must exceed the
# observed distribution. Ref: session-summary-april-27-2026-session-20.
SOFT_TIMEOUT_S = 5.5
HARD_TIMEOUT_S = 6.0
TOOL_NAME = "record_interpretation"

SYSTEM_PROMPT = """\
You are a tax-domain query interpreter for a CPA-facing retrieval \
system. The user is a CPA asking about their client's tax documents.

Your job is NOT to answer the question. Your job is to identify \
what tax forms, line numbers, and canonical concept keywords would \
help retrieve the answer from the client's documents.

Output ONLY a structured tool call with these fields:
- forms: list of form identifiers (e.g., "1040", "1120-S", \
"Schedule K", "Schedule K-1", "Form 100S"). Use canonical names.
- line_numbers: specific line numbers if mentioned or inferable.
- keywords: canonical phrasings of the tax concepts being asked \
about (e.g., "ordinary business income", "shareholder distribution").
- intent: classify the question shape — "factual_lookup" for \
"what was X," "enumeration" for "what are all X," "synthesis" \
for "what's currently active / compare across years," "advisory" \
for "what should I do." "unknown" if unclear.
- confidence: 0.0–1.0 self-assessment.
- reasoning: brief explanation (one sentence).

CRITICAL RULES:
- Return empty arrays if you are not confident. Do not guess form \
names or line numbers.
- Do not answer the underlying tax question.
- Do not invent forms that don't exist. If unsure between similar \
forms (e.g., 1040 vs 1040-SR), include both.
- Common entity types: 1040 (individual), 1120 (C-corp), \
1120-S (S-corp), 1065 (partnership), 1041 (trust), 990 (exempt). \
California state forms: 540 (individual), 100/100S (corp)."""

INTERPRETATION_TOOL = {
    "name": TOOL_NAME,
    "description": "Record the structured interpretation of a user query.",
    "input_schema": {
        "type": "object",
        "required": [
            "forms", "line_numbers", "keywords",
            "intent", "confidence", "reasoning",
        ],
        "properties": {
            "forms": {"type": "array", "items": {"type": "string"}},
            "line_numbers": {"type": "array", "items": {"type": "string"}},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "intent": {
                "type": "string",
                "enum": [
                    "factual_lookup", "enumeration",
                    "synthesis", "advisory", "unknown",
                ],
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasoning": {"type": "string"},
        },
    },
}


# ── Per-worker LRU cache (§3.7) ───────────────────────────────────────
#
# Cache key versions on PROMPT_VERSION + MODEL_ID, so any prompt or
# model change automatically invalidates without explicit flush.
# Negative caching: None values are stored explicitly (cache hit on a
# known-failed question short-circuits the LLM call).

_CACHE_MAXSIZE = 1024
_cache: OrderedDict[str, InterpretationResult | None] = OrderedDict()
_CACHE_MISS = object()  # sentinel — distinguishes "not present" from "present-with-None"


def _cache_key(question: str) -> str:
    """SHA256 over normalized question + prompt version + model id."""
    normalized = question.lower().strip()
    material = f"{normalized}|{PROMPT_VERSION}|{MODEL_ID}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _cache_get(key: str):
    """Return cached value (which may be None) or _CACHE_MISS sentinel."""
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return _CACHE_MISS


def _cache_set(key: str, value: InterpretationResult | None) -> None:
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = value
    if len(_cache) > _CACHE_MAXSIZE:
        _cache.popitem(last=False)


def _cache_clear() -> None:
    """Test/debug helper. Not called in production code paths."""
    _cache.clear()


# ── Lazy client singleton ─────────────────────────────────────────────

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic | None:
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    _client = AsyncAnthropic(api_key=api_key)
    return _client


# ── Payload validation ────────────────────────────────────────────────

_VALID_INTENTS = {"factual_lookup", "enumeration", "synthesis", "advisory", "unknown"}


def _validate_payload(payload: dict) -> bool:
    """Validate the tool-use payload matches the expected schema."""
    required = ("forms", "line_numbers", "keywords", "intent", "confidence", "reasoning")
    if not all(k in payload for k in required):
        return False
    if not isinstance(payload["forms"], list) or not all(isinstance(x, str) for x in payload["forms"]):
        return False
    if not isinstance(payload["line_numbers"], list) or not all(isinstance(x, str) for x in payload["line_numbers"]):
        return False
    if not isinstance(payload["keywords"], list) or not all(isinstance(x, str) for x in payload["keywords"]):
        return False
    if payload["intent"] not in _VALID_INTENTS:
        return False
    if not isinstance(payload["confidence"], (int, float)) or not (0.0 <= payload["confidence"] <= 1.0):
        return False
    if not isinstance(payload["reasoning"], str):
        return False
    return True


# ── One-time Sentry alerts (deduped per process) ─────────────────────

_missing_key_alerted = False
_auth_failure_alerted = False


def _alert_missing_api_key() -> None:
    global _missing_key_alerted
    if _missing_key_alerted:
        return
    _missing_key_alerted = True
    sentry_sdk.capture_message(
        "ANTHROPIC_API_KEY missing; query interpretation disabled",
        level="error",
    )


def _alert_auth_failure() -> None:
    global _auth_failure_alerted
    if _auth_failure_alerted:
        return
    _auth_failure_alerted = True
    sentry_sdk.capture_message(
        "Anthropic auth failure on query interpretation",
        level="error",
    )


def _alert_schema_failure(payload: object) -> None:
    with sentry_sdk.push_scope() as scope:
        scope.set_extra("payload_repr", repr(payload)[:500])
        sentry_sdk.capture_message(
            "Query interpretation schema validation failed",
            level="error",
        )


# ── Per-call structured log ──────────────────────────────────────────


def _emit_log(
    *,
    question_hash: str,
    latency_ms: int,
    success: bool,
    fallback_triggered: bool,
    confidence: float | None,
    intent: str | None,
    forms_count: int | None,
    forms: list | None,
    keywords_count: int | None,
    from_cache: bool,
) -> None:
    logger.info(
        "query_interpretation",
        extra={
            "event": "query_interpretation",
            "question_hash": f"sha256:{question_hash[:16]}...",
            "model": MODEL_ID,
            "prompt_version": PROMPT_VERSION,
            "latency_ms": latency_ms,
            "success": success,
            "fallback_triggered": fallback_triggered,
            "confidence": confidence,
            "intent": intent,
            "forms_count": forms_count,
            "forms": forms or [],
            "keywords_count": keywords_count,
            "from_cache": from_cache,
        },
    )


# ── Main entry point ──────────────────────────────────────────────────


async def interpret_query_llm(
    question: str,
) -> InterpretationResult | None:
    """
    Interpret a user query into structured retrieval signals.

    Returns InterpretationResult on successful interpretation, or None
    on flag-off / missing API key / timeout / API error / low
    confidence / schema validation failure.  None is always safe —
    it signals "use dictionary-only behavior" downstream.
    """
    # 1. Flag gate — MUST be first line. When flag is off, this
    #    function is byte-equivalent to the Session 18 stub.
    if os.getenv("USE_LLM_QUERY_INTERPRETATION", "false").lower() != "true":
        return None

    # 2. Client init — returns None if ANTHROPIC_API_KEY is unset.
    #    No cache write, no per-call log. One-time Sentry alert only.
    client = _get_client()
    if client is None:
        _alert_missing_api_key()
        return None

    # 3. Cache check — after flag gate and client check, before LLM call.
    cache_key = _cache_key(question)
    t0 = time.perf_counter()
    cached = _cache_get(cache_key)
    if cached is not _CACHE_MISS:
        _emit_log(
            question_hash=cache_key,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            success=cached is not None,
            fallback_triggered=cached is None,
            confidence=cached.confidence if cached is not None else None,
            intent=cached.intent if cached is not None else None,
            forms_count=len(cached.forms) if cached is not None else None,
            forms=cached.forms if cached is not None else [],
            keywords_count=len(cached.keywords) if cached is not None else None,
            from_cache=True,
        )
        return cached  # may be InterpretationResult or None (negative cache)

    # 4. Real Haiku call with dual timeout (SDK soft + asyncio hard).
    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=MODEL_ID,
                max_tokens=512,
                temperature=0,
                timeout=SOFT_TIMEOUT_S,
                system=SYSTEM_PROMPT,
                tools=[INTERPRETATION_TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[{"role": "user",
                           "content": f"Question: {question}"}],
            ),
            timeout=HARD_TIMEOUT_S,
        )
    except anthropic.AuthenticationError:
        _alert_auth_failure()
        _cache_set(cache_key, None)
        _emit_log(
            question_hash=cache_key,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            success=False, fallback_triggered=True,
            confidence=None, intent=None,
            forms_count=None, forms=[],
            keywords_count=None, from_cache=False,
        )
        return None
    except (asyncio.TimeoutError,
            anthropic.APITimeoutError,
            anthropic.APIError):
        _cache_set(cache_key, None)
        _emit_log(
            question_hash=cache_key,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            success=False, fallback_triggered=True,
            confidence=None, intent=None,
            forms_count=None, forms=[],
            keywords_count=None, from_cache=False,
        )
        return None
    except Exception:
        sentry_sdk.capture_exception()
        _cache_set(cache_key, None)
        _emit_log(
            question_hash=cache_key,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            success=False, fallback_triggered=True,
            confidence=None, intent=None,
            forms_count=None, forms=[],
            keywords_count=None, from_cache=False,
        )
        return None

    # 5. Extract tool-use block.
    tool_block = next(
        (b for b in response.content
         if getattr(b, "type", None) == "tool_use"
         and getattr(b, "name", None) == TOOL_NAME),
        None,
    )
    if tool_block is None:
        _cache_set(cache_key, None)
        _emit_log(
            question_hash=cache_key,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            success=False, fallback_triggered=True,
            confidence=None, intent=None,
            forms_count=None, forms=[],
            keywords_count=None, from_cache=False,
        )
        return None
    payload = tool_block.input

    # 6. Schema validation.
    if not _validate_payload(payload):
        _alert_schema_failure(payload)
        _cache_set(cache_key, None)
        _emit_log(
            question_hash=cache_key,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            success=False, fallback_triggered=True,
            confidence=None, intent=None,
            forms_count=None, forms=[],
            keywords_count=None, from_cache=False,
        )
        return None

    # 7. Confidence threshold.
    if payload["confidence"] < CONFIDENCE_THRESHOLD:
        _cache_set(cache_key, None)
        _emit_log(
            question_hash=cache_key,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            success=False, fallback_triggered=True,
            confidence=payload["confidence"], intent=payload.get("intent"),
            forms_count=None, forms=[],
            keywords_count=None, from_cache=False,
        )
        return None

    # 8. Build, cache, log, and return.
    result = InterpretationResult(
        forms=payload["forms"],
        line_numbers=payload["line_numbers"],
        keywords=payload["keywords"],
        intent=payload["intent"],
        confidence=payload["confidence"],
        reasoning=payload["reasoning"],
        schema_version="v1",
    )
    _cache_set(cache_key, result)
    _emit_log(
        question_hash=cache_key,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        success=True, fallback_triggered=False,
        confidence=result.confidence, intent=result.intent,
        forms_count=len(result.forms), forms=result.forms,
        keywords_count=len(result.keywords),
        from_cache=False,
    )
    return result
