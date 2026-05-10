"""
Kickoff memo deliverable handler.

Builds the prompt for an engagement kickoff email, extracts strategy/task
references, and delegates open-items extraction to the existing GPT-4o-mini
extractor in communication_service.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.communication import OpenItem
from app.services.communication_service import extract_open_items_from_email
from app.services.deliverables._base import (
    ClientFacts,
    ContextBundle,
    DeliverableHandler,
)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_kickoff_prompt(bundle: ContextBundle, facts: ClientFacts) -> str:
    """Build the GPT-4o prompt for drafting an engagement kickoff memo."""
    recommended = [s for s in bundle.strategies if s.get("status") == "recommended"]
    client_tasks = [
        ai for ai in bundle.action_items
        if ai.get("owner_role") in ("client", "third_party")
    ]

    sections: list[str] = []

    # System instruction
    sections.append(
        "You are a CPA drafting a professional engagement kickoff email to a client. "
        "This email introduces the recommended tax strategies for the year and lists "
        "the client-facing implementation tasks. Be specific, personalized, and concise. "
        "Do NOT compute tax amounts or make guarantees about savings. "
        "Return ONLY the email body (no greeting, no sign-off — the template adds those)."
    )

    # Client facts
    sections.append(
        f"\n--- CLIENT ---\n"
        f"Name: {facts.name}\n"
        f"Entity type: {facts.entity_type or 'Individual'}\n"
        f"Tax year: {facts.tax_year}"
    )

    # Strategies
    if recommended:
        lines = ["\n--- RECOMMENDED STRATEGIES ---"]
        for s in recommended:
            name = s.get("name", s.get("strategy", "Unknown"))
            category = s.get("category", "")
            impact = s.get("estimated_impact")
            line = f"• {name}"
            if category:
                line += f" ({category})"
            if impact:
                line += f" — est. ${impact:,.0f}"
            lines.append(line)
            if s.get("notes"):
                lines.append(f"  Notes: {s['notes']}")
        sections.append("\n".join(lines))
    else:
        sections.append(
            "\n--- STRATEGIES ---\n"
            "We are still finalizing strategy recommendations for this client. "
            "Focus the email on the implementation tasks below and note that "
            "strategy recommendations will follow in a separate communication."
        )

    # Client-facing tasks
    if client_tasks:
        lines = ["\n--- CLIENT-FACING TASKS ---"]
        for ai in client_tasks:
            text = ai.get("text", "")
            role = ai.get("owner_role", "")
            due = ai.get("due_date", "")
            line = f"• {text}"
            if role == "third_party":
                line += " [third-party action]"
            if due:
                line += f" (due {due})"
            lines.append(line)
        sections.append("\n".join(lines))

    # Journal context (recent events)
    if bundle.journal:
        lines = ["\n--- RECENT CLIENT EVENTS (last 30 days) ---"]
        for entry in bundle.journal[:5]:
            title = entry.get("title", "")
            date_str = entry.get("date", "")
            lines.append(f"• [{date_str}] {title}")
        sections.append("\n".join(lines))

    # Output instruction
    sections.append(
        f"\n--- OUTPUT ---\n"
        f"Subject line (pre-filled, do not change): "
        f"Engagement kickoff — {facts.name} — {facts.tax_year}\n\n"
        f"Write the email body now."
    )

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# References extractor
# ---------------------------------------------------------------------------


def _extract_strategies_and_tasks(bundle: ContextBundle, facts: ClientFacts) -> dict:
    """Extract structured references from the context bundle."""
    recommended = [s for s in bundle.strategies if s.get("status") == "recommended"]
    client_tasks = [
        ai for ai in bundle.action_items
        if ai.get("owner_role") in ("client", "third_party")
    ]

    # Dedup tasks by text (same logical task may exist as multiple ActionItem rows)
    seen_texts: set[str] = set()
    deduped_tasks = []
    for ai in client_tasks:
        text = ai.get("text", "")
        if text not in seen_texts:
            seen_texts.add(text)
            deduped_tasks.append(ai)

    return {
        "strategies": [
            {"id": s.get("id", ""), "name": s.get("name", s.get("strategy", ""))}
            for s in recommended
        ],
        "tasks": [
            {
                "id": ai.get("id", ""),
                "name": ai.get("text", ""),
                "owner_role": ai.get("owner_role", ""),
                "due_date": ai.get("due_date"),
                "strategy_name": ai.get("strategy_name", ""),
            }
            for ai in deduped_tasks
        ],
    }


# ---------------------------------------------------------------------------
# Open-items extractor (delegates to existing GPT-4o-mini extractor)
# ---------------------------------------------------------------------------


def _extract_open_items_from_kickoff(
    body: str,
    comm_id: UUID,
    asked_date: datetime,
) -> list[OpenItem]:
    """
    Extract open items from a sent kickoff memo body.

    Delegates to the existing GPT-4o-mini extractor (April 7 ship) and
    shapes the results into OpenItem instances.
    """
    raw = extract_open_items_from_email(body)
    return [
        OpenItem(
            question=item["question"],
            asked_in_email_id=comm_id,
            asked_date=asked_date,
        )
        for item in raw
    ]


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------

KICKOFF_MEMO_HANDLER = DeliverableHandler(
    deliverable_key="kickoff_memo",
    context_purpose="engagement_kickoff",
    thread_type="engagement_year",
    build_prompt=_build_kickoff_prompt,
    extract_references=_extract_strategies_and_tasks,
    extract_open_items=_extract_open_items_from_kickoff,
)
