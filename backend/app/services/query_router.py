"""
Query classifier and model router for the Advisory Intelligence Layer.

Classifies user questions into three tiers using GPT-4o-mini:
  - factual   → GPT-4o-mini  (fast, cheap lookups)
  - synthesis  → Claude Sonnet 4.6 (cross-document analysis)
  - strategic  → Claude Opus 4.6 (deep reasoning & recommendations)

Cascading fallback on quota exhaustion:
  strategic → Opus (quota) → Sonnet (quota) → GPT-4o-mini
  synthesis → Sonnet (quota) → GPT-4o-mini

Falls back to GPT-4o-mini if ANTHROPIC_API_KEY is not configured.
Enforces total query limit before any model routing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.prompt_templates import build_strategic_prompt, build_synthesis_prompt
from app.services.subscription_service import (
    check_opus_quota,
    check_sonnet_quota,
    check_total_query_quota,
    increment_usage,
)
from app.services.token_tracking_service import log_token_usage

logger = logging.getLogger(__name__)

_anthropic_warned = False

_VALID_QUERY_TYPES = frozenset({"factual", "synthesis", "strategic"})

CLASSIFIER_SYSTEM_PROMPT = """\
You are a query classifier for a CPA advisory platform. Classify the user's question into exactly one category.

FACTUAL — Direct data retrieval from documents. The answer exists verbatim or nearly verbatim in the uploaded documents:
- "What was the AGI?"
- "Show me the deductions on Schedule A"
- "What is the client's filing status?"
- "How much was the total income?"
- "What date was the engagement letter signed?"

SYNTHESIS — Compare, summarize, contrast, or analyze information across one or more documents. Requires reading comprehension and organization but NOT generating novel recommendations:
- "Compare 2023 vs 2024 tax returns"
- "Summarize all action items for this client"
- "What changed between these two documents?"
- "Give me an overview of this client's financial situation"
- "List all the K-1 entities and their income"

STRATEGIC — Generate recommendations, strategies, predictions, or forward-looking advice. Requires reasoning beyond what's in the documents:
- "What tax-loss harvesting opportunities should we explore?"
- "Should this client restructure as an S-corp?"
- "What estate planning strategies would you recommend?"
- "How can we reduce their effective tax rate?"
- "What are the risks of this entity structure?"

Respond with ONLY the word "factual", "synthesis", or "strategic". Nothing else."""


async def classify_query(
    question: str,
    *,
    db: Optional[Session] = None,
    user_id: Optional[str] = None,
    client_id: Optional[UUID] = None,
) -> str:
    """Classify a user question as 'factual', 'synthesis', or 'strategic' using GPT-4o-mini."""
    try:
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0,
            max_tokens=10,
        )
        result = (response.choices[0].message.content or "").strip().lower()
        query_type = result if result in _VALID_QUERY_TYPES else "factual"
        logger.info("Query classified as %s: %s", query_type, question[:80])

        # Log classification token usage
        if db and user_id:
            try:
                usage = response.usage
                log_token_usage(
                    db,
                    user_id=user_id,
                    client_id=client_id,
                    query_type="classification",
                    model="gpt-4o-mini",
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    endpoint="classify",
                )
            except Exception:
                logger.error("Failed to log classify token usage", exc_info=True)

        return query_type
    except Exception:
        logger.exception("Query classification failed — defaulting to factual")
        return "factual"


# ─── Analysis tier labels (user-facing) ─────────────────────────────────────

_TIER_MAP = {
    "gpt-4o-mini": "standard",
    "claude-sonnet-4.6": "advanced",
    "claude-opus-4.6": "premium",
}


def _analysis_tier(model_used: str) -> str:
    return _TIER_MAP.get(model_used, "standard")


def _build_result(
    answer: str,
    model_used: str,
    query_type: str,
    *,
    quota_remaining: int | None = None,
    quota_warning: str | None = None,
    quota_warning_message: str | None = None,
) -> dict[str, Any]:
    """Build a standardized route_completion result dict."""
    return {
        "answer": answer,
        "model_used": model_used,
        "analysis_tier": _analysis_tier(model_used),
        "query_type": query_type,
        "quota_remaining": quota_remaining,
        "quota_warning": quota_warning,
        "quota_warning_message": quota_warning_message,
    }


async def route_completion(
    query_type: str,
    system_prompt: str,
    question: str,
    *,
    db: Optional[Session] = None,
    user_id: Optional[str] = None,
    client_id: Optional[UUID] = None,
    client_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Route to the appropriate model based on query_type with cascading fallback.

    1. Check total query quota — hard block if exceeded.
    2. Apply classification cascade:
       strategic → Opus (quota) → Sonnet (quota) → GPT-4o-mini
       synthesis → Sonnet (quota) → GPT-4o-mini
       factual   → GPT-4o-mini

    Returns dict with: answer, model_used, analysis_tier, query_type,
                        quota_remaining, quota_warning, quota_warning_message.
    """
    global _anthropic_warned
    settings = get_settings()

    # Track the original classification for logging
    original_query_type = query_type

    quota_remaining: int | None = None
    quota_warning: str | None = None
    quota_warning_message: str | None = None

    # ── GATE: Total query quota check ───────────────────────────────────
    if db and user_id:
        try:
            total_quota = check_total_query_quota(db, user_id)
            if not total_quota["allowed"]:
                logger.info(
                    "Total query limit reached for user %s (used=%d/%d)",
                    user_id, total_quota["used"], total_quota["limit"],
                )
                return _build_result(
                    answer=(
                        "You've reached your monthly query limit. "
                        "Please upgrade your plan for additional queries."
                    ),
                    model_used="none",
                    query_type=query_type,
                    quota_warning_message=(
                        "You've reached your monthly query limit. "
                        "Upgrade your plan for additional queries."
                    ),
                )
        except Exception:
            logger.error("Total quota check failed — allowing query", exc_info=True)

    # ── Strategic path: try Opus → Sonnet → GPT-4o-mini ─────────────────
    if query_type == "strategic" and db and user_id and settings.anthropic_api_key:
        try:
            opus_quota = check_opus_quota(db, user_id)
            if not opus_quota["allowed"]:
                logger.info(
                    "Strategic query: Opus quota exceeded for user %s (used=%d/%d), trying Sonnet",
                    user_id, opus_quota["used"], opus_quota["limit"],
                )
                # Will be overwritten if Sonnet also fails
                quota_warning_message = (
                    "Your premium analysis quota has been reached for this month. "
                    "This response used advanced analysis instead."
                )
                query_type = "synthesis"
        except Exception:
            logger.error("Opus quota check failed — allowing query", exc_info=True)

    if query_type == "strategic" and settings.anthropic_api_key:
        strategic_system = build_strategic_prompt(client_type) + "\n\n" + system_prompt
        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model="claude-opus-4-20250514",
                max_tokens=4000,
                system=strategic_system,
                messages=[{"role": "user", "content": question}],
                temperature=0.2,
            )
            answer = response.content[0].text
            model_used = "claude-opus-4.6"
            logger.info("Strategic query answered by Claude Opus 4.6")

            if db and user_id:
                try:
                    usage = response.usage
                    log_token_usage(
                        db,
                        user_id=user_id,
                        client_id=client_id,
                        query_type="strategic",
                        model="claude-opus-4-20250514",
                        prompt_tokens=usage.input_tokens if usage else 0,
                        completion_tokens=usage.output_tokens if usage else 0,
                        endpoint="chat",
                    )
                except Exception:
                    logger.error("Failed to log Opus token usage", exc_info=True)

            return _build_result(
                answer, model_used, "strategic",
                quota_remaining=quota_remaining,
                quota_warning=quota_warning,
                quota_warning_message=quota_warning_message,
            )
        except Exception:
            logger.exception("Claude Opus call failed — falling back to Sonnet")
            query_type = "synthesis"

    # ── Synthesis path: try Sonnet → GPT-4o-mini ────────────────────────
    if query_type == "synthesis" and db and user_id:
        try:
            sonnet_quota = check_sonnet_quota(db, user_id)
            quota_remaining = sonnet_quota["remaining"]

            if not sonnet_quota["allowed"]:
                logger.info(
                    "Sonnet quota exceeded for user %s (tier=%s, used=%d/%d)",
                    user_id, sonnet_quota["tier"], sonnet_quota["used"], sonnet_quota["limit"],
                )
                if sonnet_quota["limit"] == 0:
                    quota_warning_message = (
                        "Your plan does not include advanced analysis. "
                        "Upgrade to Professional for deeper insights."
                    )
                elif original_query_type == "strategic":
                    # Both Opus and Sonnet exhausted
                    quota_warning_message = (
                        "Your advanced and premium analysis quotas have been reached "
                        "for this month. This response used standard analysis. "
                        "Upgrade for more advanced analyses."
                    )
                else:
                    quota_warning_message = (
                        "Your advanced analysis quota has been reached for this month. "
                        "This response used standard analysis."
                    )
                quota_remaining = 0
                query_type = "factual"
        except Exception:
            logger.error("Sonnet quota check failed — allowing query", exc_info=True)

    if query_type == "synthesis" and settings.anthropic_api_key:
        synthesis_system = build_synthesis_prompt(client_type) + "\n\n" + system_prompt
        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=synthesis_system,
                messages=[{"role": "user", "content": question}],
                temperature=0.2,
            )
            answer = response.content[0].text
            model_used = "claude-sonnet-4.6"
            logger.info("Synthesis query answered by Claude Sonnet 4.6")

            # Log Anthropic token usage
            if db and user_id:
                try:
                    usage = response.usage
                    log_token_usage(
                        db,
                        user_id=user_id,
                        client_id=client_id,
                        query_type=original_query_type,
                        model="claude-sonnet-4-20250514",
                        prompt_tokens=usage.input_tokens if usage else 0,
                        completion_tokens=usage.output_tokens if usage else 0,
                        endpoint="chat",
                    )
                except Exception:
                    logger.error("Failed to log Claude token usage", exc_info=True)

            # Increment usage and compute warning
            if db and user_id:
                try:
                    increment_usage(db, user_id, original_query_type)
                    updated_quota = check_sonnet_quota(db, user_id)
                    quota_remaining = updated_quota["remaining"]
                    if quota_remaining is not None and quota_remaining < 10:
                        quota_warning = (
                            f"You have {quota_remaining} advanced analysis "
                            f"quer{'y' if quota_remaining == 1 else 'ies'} "
                            f"remaining this month."
                        )
                except Exception:
                    logger.error("Failed to increment usage", exc_info=True)

            return _build_result(
                answer, model_used, original_query_type,
                quota_remaining=quota_remaining,
                quota_warning=quota_warning,
                quota_warning_message=quota_warning_message,
            )
        except Exception:
            logger.exception("Claude call failed — falling back to GPT-4o-mini")
            # Fall through to GPT-4o-mini below

    if query_type in ("synthesis", "strategic") and not settings.anthropic_api_key and not _anthropic_warned:
        logger.warning(
            "ANTHROPIC_API_KEY not set — all queries will use GPT-4o-mini. "
            "Set ANTHROPIC_API_KEY to enable Claude for synthesis/strategic queries."
        )
        _anthropic_warned = True

    # ── Factual queries (or fallback) ───────────────────────────────────
    oai = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=1_500,
    )
    answer = response.choices[0].message.content or "No answer generated."
    model_used = "gpt-4o-mini"
    logger.info("Query answered by GPT-4o-mini")

    # Log OpenAI token usage
    if db and user_id:
        try:
            usage = response.usage
            log_token_usage(
                db,
                user_id=user_id,
                client_id=client_id,
                query_type=original_query_type,
                model="gpt-4o-mini",
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                endpoint="chat",
            )
        except Exception:
            logger.error("Failed to log GPT token usage", exc_info=True)

    return _build_result(
        answer, model_used, original_query_type,
        quota_remaining=quota_remaining,
        quota_warning=quota_warning,
        quota_warning_message=quota_warning_message,
    )


async def route_completion_stream(
    query_type: str,
    system_prompt: str,
    question: str,
    *,
    db: Optional[Session] = None,
    user_id: Optional[str] = None,
    client_id: Optional[UUID] = None,
    client_type: Optional[str] = None,
):
    """
    Streaming variant of route_completion. Yields (token, None) for content
    chunks and (None, metadata_dict) as the final item with model_used etc.

    Supports the three-level cascade:
      strategic → Opus N/A for streaming (downgrade to synthesis)
      synthesis → Sonnet (quota) → GPT-4o-mini
      factual → GPT-4o-mini
    """
    global _anthropic_warned
    settings = get_settings()

    original_query_type = query_type

    quota_remaining: int | None = None
    quota_warning: str | None = None
    quota_warning_message: str | None = None
    model_used = "gpt-4o-mini"

    # ── GATE: Total query quota check ───────────────────────────────────
    if db and user_id:
        try:
            total_quota = check_total_query_quota(db, user_id)
            if not total_quota["allowed"]:
                logger.info(
                    "Streaming: Total query limit reached for user %s (used=%d/%d)",
                    user_id, total_quota["used"], total_quota["limit"],
                )
                error_msg = (
                    "You've reached your monthly query limit. "
                    "Please upgrade your plan for additional queries."
                )
                import json as _json
                yield None, {
                    "model_used": "none",
                    "analysis_tier": "standard",
                    "query_type": query_type,
                    "quota_remaining": 0,
                    "quota_warning": None,
                    "quota_warning_message": (
                        "You've reached your monthly query limit. "
                        "Upgrade your plan for additional queries."
                    ),
                    "error": error_msg,
                }
                return
        except Exception:
            logger.error("Total quota check failed — allowing query", exc_info=True)

    # Strategic streaming: downgrade to synthesis (streaming doesn't support Opus)
    if query_type == "strategic":
        query_type = "synthesis"

    # Check Sonnet quota for synthesis queries
    if query_type == "synthesis" and db and user_id:
        try:
            sonnet_quota = check_sonnet_quota(db, user_id)
            quota_remaining = sonnet_quota["remaining"]
            if not sonnet_quota["allowed"]:
                if original_query_type == "strategic":
                    quota_warning_message = (
                        "Your advanced and premium analysis quotas have been reached "
                        "for this month. This response used standard analysis. "
                        "Upgrade for more advanced analyses."
                    )
                else:
                    quota_warning_message = (
                        "Your advanced analysis quota has been reached for this month. "
                        "This response used standard analysis."
                    )
                query_type = "factual"
        except Exception:
            logger.error("Quota check failed — allowing query", exc_info=True)

    # Synthesis queries: stream from Claude Sonnet if available
    if query_type == "synthesis" and settings.anthropic_api_key:
        synthesis_system = build_synthesis_prompt(client_type) + "\n\n" + system_prompt
        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            full_answer = ""
            async with client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=synthesis_system,
                messages=[{"role": "user", "content": question}],
                temperature=0.2,
            ) as stream:
                async for text in stream.text_stream:
                    full_answer += text
                    yield text, None

            model_used = "claude-sonnet-4.6"
            logger.info("Streaming synthesis query answered by Claude Sonnet 4.6")

            # Increment usage
            if db and user_id:
                try:
                    increment_usage(db, user_id, original_query_type)
                    updated_quota = check_sonnet_quota(db, user_id)
                    quota_remaining = updated_quota["remaining"]
                    if quota_remaining is not None and quota_remaining < 10:
                        quota_warning = (
                            f"You have {quota_remaining} advanced analysis "
                            f"quer{'y' if quota_remaining == 1 else 'ies'} "
                            f"remaining this month."
                        )
                except Exception:
                    logger.error("Failed to increment usage", exc_info=True)

            # Log token usage
            if db and user_id:
                try:
                    final_message = await stream.get_final_message()
                    usage = final_message.usage
                    log_token_usage(
                        db, user_id=user_id, client_id=client_id,
                        query_type=original_query_type,
                        model="claude-sonnet-4-20250514",
                        prompt_tokens=usage.input_tokens if usage else 0,
                        completion_tokens=usage.output_tokens if usage else 0,
                        endpoint="chat_stream",
                    )
                except Exception:
                    logger.error("Failed to log Claude stream token usage", exc_info=True)

            yield None, {
                "model_used": model_used,
                "analysis_tier": _analysis_tier(model_used),
                "query_type": original_query_type,
                "quota_remaining": quota_remaining,
                "quota_warning": quota_warning,
                "quota_warning_message": quota_warning_message,
            }
            return
        except Exception:
            logger.exception("Claude streaming failed — falling back to GPT-4o-mini")

    # Factual queries (or fallback): stream from GPT-4o-mini
    oai = AsyncOpenAI(api_key=settings.openai_api_key)
    stream = await oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=1_500,
        stream=True,
    )

    full_answer = ""
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            full_answer += delta.content
            yield delta.content, None

    logger.info("Streaming query answered by GPT-4o-mini")

    # Log token usage
    if db and user_id:
        try:
            log_token_usage(
                db, user_id=user_id, client_id=client_id,
                query_type=original_query_type, model="gpt-4o-mini",
                prompt_tokens=0, completion_tokens=0,
                endpoint="chat_stream",
            )
        except Exception:
            logger.error("Failed to log GPT stream token usage", exc_info=True)

    yield None, {
        "model_used": model_used,
        "analysis_tier": _analysis_tier(model_used),
        "query_type": original_query_type,
        "quota_remaining": quota_remaining,
        "quota_warning": quota_warning,
        "quota_warning_message": quota_warning_message,
    }
