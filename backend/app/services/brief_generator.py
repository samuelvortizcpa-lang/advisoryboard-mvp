"""
Client brief generator: uses GPT-4o to produce a one-click meeting prep brief.

Gathers documents, action items, and client metadata, then produces a
structured markdown brief suitable for quick pre-meeting review.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

BRIEF_MODEL = "gpt-4o"  # Use GPT-4o for higher quality briefs

BRIEF_SYSTEM_PROMPT = """\
You are an expert CPA meeting preparation assistant. Your job is to create a concise,
actionable client brief that a CPA can review in 2-3 minutes before a meeting.

Produce a well-structured markdown brief with these sections:

## Client Snapshot
A 2-3 sentence executive summary of who this client is and their current situation.

## Key Documents Summary
Summarize the most important documents on file, highlighting critical numbers,
dates, and findings. Group by document type when possible.

## Open Action Items
List pending action items with their priority and due dates.
Flag any overdue items prominently.

## Discussion Points
Based on the documents and action items, suggest 3-5 specific talking points
for the upcoming meeting. Be concrete — reference specific numbers, deadlines,
or documents.

## Communication History
If recent communications are provided, summarize the latest outreach and
any follow-ups that may be needed.

## Strategy Overview
If strategy status data is provided, note which strategies are implemented,
recommended, or pending review. Flag any high-impact opportunities.

## Risk Flags
Highlight any potential risks, compliance issues, approaching deadlines, or
items that need urgent attention.

Guidelines:
- Be concise and scannable — use bullet points and bold for key figures
- Reference specific document names and dates
- Prioritize actionable information over general summaries
- If data is limited, note gaps and suggest what information to request
- Use professional CPA terminology where appropriate
"""

BRIEF_USER_PROMPT = """\
Generate a meeting prep brief for the following client.

{assembled_context}
"""


def _openai() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=get_settings().openai_api_key)


async def generate_brief(
    db: Session,
    client_id: UUID,
    user_id: str,
) -> dict:
    """
    Generate a meeting prep brief for a client.

    Returns::

        {
            "content": str,           # markdown brief
            "document_count": int,
            "action_item_count": int,
            "metadata": dict,
        }
    """
    start_time = time.time()

    # --- Assemble client context via the unified context assembler ---
    from app.services.context_assembler import (
        ContextPurpose,
        assemble_context,
        format_context_for_prompt,
    )

    ai_ctx = await assemble_context(
        db, client_id=client_id, user_id=user_id,
        purpose=ContextPurpose.BRIEF,
    )
    formatted_context = format_context_for_prompt(ai_ctx, ContextPurpose.BRIEF)

    doc_count = len(ai_ctx.documents_summary)
    action_count = len(ai_ctx.action_items)

    user_prompt = BRIEF_USER_PROMPT.format(assembled_context=formatted_context)

    # Call GPT-4o
    openai_client = _openai()
    response = await openai_client.chat.completions.create(
        model=BRIEF_MODEL,
        messages=[
            {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2_000,
    )

    content = response.choices[0].message.content or "Brief generation failed."

    elapsed = round(time.time() - start_time, 2)
    usage = response.usage

    metadata = {
        "model": BRIEF_MODEL,
        "generation_time_seconds": elapsed,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }

    # Log token usage for cost tracking
    try:
        from app.services.token_tracking_service import log_token_usage
        log_token_usage(
            db,
            user_id=user_id,
            client_id=client_id,
            query_type="brief",
            model=BRIEF_MODEL,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            endpoint="brief",
        )
    except Exception:
        logger.error("Failed to log brief token usage", exc_info=True)

    logger.info(
        "Brief generated for client %s: %d docs, %d actions, %.1fs",
        client_id, doc_count, action_count, elapsed,
    )

    return {
        "content": content,
        "document_count": doc_count,
        "action_item_count": action_count,
        "metadata": metadata,
    }
