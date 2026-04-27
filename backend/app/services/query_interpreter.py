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

from dataclasses import dataclass, field
from typing import Literal


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


async def interpret_query_llm(
    question: str,
) -> InterpretationResult | None:
    """
    Interpret a user query into structured retrieval signals.

    STUB IMPLEMENTATION (Session 18). Always returns None.
    Returning None is the fallback signal -- caller treats it as
    "no LLM signal, use dictionary only."  This stub lets the
    integration path (Prompt 3) be written and verified end-to-end
    before the real Anthropic SDK is wired in Session 19.

    Args:
        question: the raw user query string.

    Returns:
        InterpretationResult on successful interpretation, or None
        on timeout / API error / low confidence / schema validation
        failure.  None is always safe -- it signals "use
        dictionary-only behavior" downstream.
    """
    # Session 19 will replace this stub with a real Anthropic API
    # call.  Until then, returning None exercises the fallback path
    # -- which is the most important path to get right (it's what
    # runs whenever the LLM fails for any reason).
    return None
