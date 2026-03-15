"""
Query classifier and model router for the Advisory Intelligence Layer.

Classifies user questions as "factual" or "strategic" using GPT-4o-mini,
then routes to the appropriate model:
  - factual  → GPT-4o-mini  (fast, cheap lookups)
  - strategic → Claude Sonnet 4.6 (deep analysis & reasoning)

Falls back to GPT-4o-mini if ANTHROPIC_API_KEY is not configured.
Enforces subscription quota for strategic queries.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.prompt_templates import build_strategic_prompt
from app.services.token_tracking_service import log_token_usage

logger = logging.getLogger(__name__)

_anthropic_warned = False

CLASSIFIER_SYSTEM_PROMPT = """\
You are a query classifier for a CPA advisory platform. Classify the user's question into exactly one category.

FACTUAL — Questions that ask for specific data points, numbers, dates, or facts from documents:
- "What is the total income on Line 9?"
- "What was the AGI in 2024?"
- "How much is Box 1 on the W-2?"
- "When was this document uploaded?"
- "What deductions are listed on Schedule A?"

STRATEGIC — Questions that require analysis, interpretation, comparison, planning, or advice:
- "What tax-loss harvesting opportunities should we explore?"
- "How does 2023 compare to 2024?"
- "What strategies could reduce their tax burden?"
- "Should they convert to an S-Corp?"
- "What are the risks in their current structure?"
- "Summarize the key issues for this client"
- "What should I discuss in the meeting?"

Respond with ONLY the word "factual" or "strategic". Nothing else."""


async def classify_query(
    question: str,
    *,
    db: Optional[Session] = None,
    user_id: Optional[str] = None,
    client_id: Optional[UUID] = None,
) -> str:
    """Classify a user question as 'factual' or 'strategic' using GPT-4o-mini."""
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
        query_type = "strategic" if "strategic" in result else "factual"
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
    Route to the appropriate model based on query_type.

    Returns dict with: answer, model_used, quota_remaining, quota_warning.
    """
    global _anthropic_warned
    settings = get_settings()

    quota_remaining: int | None = None
    quota_warning: str | None = None

    # Check quota for strategic queries
    if query_type == "strategic" and db and user_id:
        try:
            from app.services.subscription_service import check_quota, increment_usage

            quota = check_quota(db, user_id)
            quota_remaining = quota["remaining"]

            if not quota["allowed"]:
                # Quota exceeded or tier doesn't allow strategic — fall back
                logger.info(
                    "Strategic query downgraded to factual for user %s (tier=%s, used=%d/%d)",
                    user_id, quota["tier"], quota["used"], quota["limit"],
                )
                if quota["limit"] == 0:
                    quota_warning = (
                        "Your plan does not include strategic analysis. "
                        "Upgrade to Professional for deep analysis with Claude."
                    )
                else:
                    quota_warning = (
                        "Strategic query limit reached for this month. "
                        "Responses are using the standard model."
                    )
                quota_remaining = 0
                # Fall through to GPT-4o-mini path below
                query_type = "factual"
        except Exception:
            logger.error("Quota check failed — allowing query", exc_info=True)

    if query_type == "strategic" and settings.anthropic_api_key:
        # Build enhanced strategic prompt with domain-specific guidance
        strategic_system = build_strategic_prompt(client_type) + "\n\n" + system_prompt
        # Route to Claude Sonnet 4.6
        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=strategic_system,
                messages=[{"role": "user", "content": question}],
                temperature=0.2,
            )
            answer = response.content[0].text
            logger.info("Strategic query answered by Claude Sonnet 4.6")

            # Log Anthropic token usage
            if db and user_id:
                try:
                    usage = response.usage
                    log_token_usage(
                        db,
                        user_id=user_id,
                        client_id=client_id,
                        query_type=query_type,
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
                    from app.services.subscription_service import increment_usage, check_quota
                    increment_usage(db, user_id, "strategic")
                    updated_quota = check_quota(db, user_id)
                    quota_remaining = updated_quota["remaining"]
                    if quota_remaining is not None and quota_remaining < 10:
                        quota_warning = (
                            f"You have {quota_remaining} strategic "
                            f"quer{'y' if quota_remaining == 1 else 'ies'} "
                            f"remaining this month."
                        )
                except Exception:
                    logger.error("Failed to increment usage", exc_info=True)

            return {
                "answer": answer,
                "model_used": "claude-sonnet-4.6",
                "quota_remaining": quota_remaining,
                "quota_warning": quota_warning,
            }
        except Exception:
            logger.exception("Claude call failed — falling back to GPT-4o-mini")
            # Fall through to GPT-4o-mini below

    if query_type == "strategic" and not settings.anthropic_api_key and not _anthropic_warned:
        logger.warning(
            "ANTHROPIC_API_KEY not set — all queries will use GPT-4o-mini. "
            "Set ANTHROPIC_API_KEY to enable Claude for strategic queries."
        )
        _anthropic_warned = True

    # Factual queries (or fallback)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.1,
        max_tokens=1_500,
    )
    answer = response.choices[0].message.content or "No answer generated."
    logger.info("Query answered by GPT-4o-mini")

    # Log OpenAI token usage
    if db and user_id:
        try:
            usage = response.usage
            log_token_usage(
                db,
                user_id=user_id,
                client_id=client_id,
                query_type=query_type,
                model="gpt-4o-mini",
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                endpoint="chat",
            )
        except Exception:
            logger.error("Failed to log GPT token usage", exc_info=True)

    return {
        "answer": answer,
        "model_used": "gpt-4o-mini",
        "quota_remaining": quota_remaining,
        "quota_warning": quota_warning,
    }
