"""
Query classifier and model router for the Advisory Intelligence Layer.

Classifies user questions as "factual" or "strategic" using GPT-4o-mini,
then routes to the appropriate model:
  - factual  → GPT-4o-mini  (fast, cheap lookups)
  - strategic → Claude Sonnet 4.6 (deep analysis & reasoning)

Falls back to GPT-4o-mini if ANTHROPIC_API_KEY is not configured.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
) -> tuple[str, str]:
    """
    Route to the appropriate model based on query_type.

    Returns (answer_text, model_used).
    """
    global _anthropic_warned
    settings = get_settings()

    if query_type == "strategic" and settings.anthropic_api_key:
        # Route to Claude Sonnet 4.6
        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=system_prompt,
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

            return answer, "claude-sonnet-4.6"
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

    return answer, "gpt-4o-mini"
