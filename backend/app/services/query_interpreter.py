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
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal

import anthropic
from anthropic import AsyncAnthropic


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
SOFT_TIMEOUT_S = 1.5
HARD_TIMEOUT_S = 2.0
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
    #    No cache write here: don't cache config failures.
    client = _get_client()
    if client is None:
        return None

    # 3. Cache check — after flag gate and client check, before LLM call.
    cache_key = _cache_key(question)
    cached = _cache_get(cache_key)
    if cached is not _CACHE_MISS:
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
    except (asyncio.TimeoutError,
            anthropic.APITimeoutError,
            anthropic.AuthenticationError,
            anthropic.APIError):
        _cache_set(cache_key, None)
        return None
    except Exception:
        # Defensive — never crash the retrieval pipeline. Phase E
        # will add Sentry capture here.
        _cache_set(cache_key, None)
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
        return None
    payload = tool_block.input

    # 6. Schema validation.
    if not _validate_payload(payload):
        _cache_set(cache_key, None)
        return None

    # 7. Confidence threshold.
    if payload["confidence"] < CONFIDENCE_THRESHOLD:
        _cache_set(cache_key, None)
        return None

    # 8. Build, cache, and return.
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
    return result
