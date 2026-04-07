"""
Quarterly estimated tax payment email workflow.

Orchestrates context assembly, thread history, financial data extraction,
and GPT-4o draft generation for quarterly estimate emails.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.client import Client
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.services.communication_service import (
    _build_email_html,
    _html_to_text,
    get_or_create_thread,
    get_thread_history,
    get_thread_open_items,
)
from app.services.context_assembler import (
    ClientContext,
    ContextPurpose,
    assemble_context,
    format_context_for_prompt,
)

logger = logging.getLogger(__name__)

# IRS quarterly estimate due dates (month, day)
QUARTERLY_DUE_DATES = {
    1: (4, 15),
    2: (6, 15),
    3: (9, 15),
    4: (1, 15),  # January 15 of the next year
}


async def draft_quarterly_estimate_email(
    db: Session,
    client_id: UUID,
    user_id: str,
    tax_year: int,
    quarter: int,
) -> Dict[str, Any]:
    """
    Orchestrate the complete quarterly estimate email workflow.

    Returns a dict with subject, body_html, body_text, thread_id,
    open_items_from_prior, and financial_context_used.
    """
    from openai import AsyncOpenAI

    settings = get_settings()
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    # --- Resolve client, user, firm ---
    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise ValueError("Client not found")

    db_user = db.query(User).filter(User.clerk_id == user_id).first()
    preparer_name = "Your advisor"
    preparer_firm = ""
    scheduling_url = ""
    if db_user:
        parts = [db_user.first_name or "", db_user.last_name or ""]
        preparer_name = " ".join(p for p in parts if p).strip() or "Your advisor"
        scheduling_url = db_user.scheduling_url or ""
        member = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active.is_(True),
            )
            .first()
        )
        if member:
            org = db.query(Organization).filter(Organization.id == member.org_id).first()
            if org and org.org_type != "personal":
                preparer_firm = org.name

    # ── Step 1: Context assembly ──────────────────────────────────────────
    ai_ctx = await assemble_context(
        db,
        client_id=client_id,
        user_id=user_id,
        purpose=ContextPurpose.QUARTERLY_ESTIMATE,
        options={"tax_year": tax_year, "quarter": quarter},
    )
    formatted_context = format_context_for_prompt(ai_ctx, ContextPurpose.QUARTERLY_ESTIMATE)

    # ── Step 2: Thread history ────────────────────────────────────────────
    thread_id = get_or_create_thread(
        db,
        client_id=client_id,
        thread_type="quarterly_estimate",
        thread_year=tax_year,
        thread_quarter=quarter,
    )

    thread_comms = get_thread_history(db, client_id, thread_id)
    open_items = get_thread_open_items(db, client_id, thread_id)

    # Build thread history summary
    thread_history_summary = _build_thread_summary(thread_comms)
    open_items_text = _build_open_items_text(open_items)

    # ── Step 3: Financial context ─────────────────────────────────────────
    financial_summary, financial_context_used = _extract_financial_context(
        ai_ctx, tax_year, quarter,
    )

    # ── Step 4: Draft generation ──────────────────────────────────────────
    due_date = _get_due_date(tax_year, quarter)

    system_prompt = _build_system_prompt(quarter, tax_year, due_date)

    user_message = (
        f"CLIENT CONTEXT:\n{formatted_context}\n\n"
        f"PRIOR EMAILS IN THIS THREAD:\n{thread_history_summary}\n\n"
        f"UNRESOLVED QUESTIONS FROM PRIOR EMAILS:\n{open_items_text}\n\n"
        f"FINANCIAL DATA:\n{financial_summary}"
    )

    body_response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
        max_tokens=1200,
    )
    ai_body = body_response.choices[0].message.content.strip()

    subject_response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate a professional email subject line for a quarterly estimated "
                    "tax payment email. Include the client name, quarter, and year. "
                    "5-12 words. Return ONLY the subject line."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Client name: {client.name}\n"
                    f"Quarter: Q{quarter}\n"
                    f"Tax year: {tax_year}\n\n"
                    f"Email body:\n{ai_body[:500]}"
                ),
            },
        ],
        temperature=0.5,
        max_tokens=30,
    )
    ai_subject = subject_response.choices[0].message.content.strip().strip('"')

    # ── Step 5: Build HTML and return ─────────────────────────────────────
    body_html = _build_email_html(
        client_name=client.name,
        body_text=ai_body,
        preparer_name=preparer_name,
        preparer_firm=preparer_firm,
        scheduling_url=scheduling_url,
    )
    body_text = _html_to_text(body_html)

    return {
        "subject": ai_subject,
        "body_html": body_html,
        "body_text": body_text,
        "thread_id": str(thread_id),
        "thread_type": "quarterly_estimate",
        "thread_year": tax_year,
        "thread_quarter": quarter,
        "open_items_from_prior": [
            {"question": item.question, "status": item.status}
            for item in open_items
        ],
        "financial_context_used": financial_context_used,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_due_date(tax_year: int, quarter: int) -> str:
    """Return the IRS due date string for a quarterly estimate."""
    month, day = QUARTERLY_DUE_DATES.get(quarter, (4, 15))
    year = tax_year + 1 if quarter == 4 else tax_year
    return date(year, month, day).strftime("%B %d, %Y")


def _build_thread_summary(comms: list) -> str:
    """Summarize prior emails in the thread for the AI prompt."""
    if not comms:
        return "No prior emails in this thread."

    lines = []
    for comm in comms:
        sent = comm.sent_at.strftime("%B %d, %Y") if comm.sent_at else "Unknown date"
        subject = comm.subject or "(no subject)"
        body_preview = ""
        if comm.body_text:
            body_preview = comm.body_text[:300].replace("\n", " ")
        lines.append(f"[{sent}] Subject: {subject}")
        if body_preview:
            lines.append(f"  Preview: {body_preview}...")
        lines.append("")

    return "\n".join(lines)


def _build_open_items_text(open_items: list) -> str:
    """Format open items for the AI prompt."""
    if not open_items:
        return "No unresolved questions from prior emails."

    lines = []
    for i, item in enumerate(open_items, 1):
        question = item.question if hasattr(item, "question") else item.get("question", "")
        lines.append(f"{i}. {question}")

    return "\n".join(lines)


def _extract_financial_context(
    ctx: ClientContext,
    tax_year: int,
    quarter: int,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Extract and format financial data from the assembled context.

    Returns (formatted_summary, context_used_list).
    """
    lines: list[str] = []
    context_used: List[Dict[str, Any]] = []
    metrics = ctx.financial_metrics

    if not metrics:
        return "No financial metrics available.", []

    prior_year = str(tax_year - 1)
    current_year = str(tax_year)

    # Prior year metrics
    prior = metrics.get(prior_year, {})
    if prior:
        lines.append(f"TAX YEAR {prior_year} (PRIOR YEAR):")
        for name in ["adjusted_gross_income", "total_tax", "total_income",
                      "taxable_income", "self_employment_tax"]:
            info = prior.get(name)
            if info and info.get("value") is not None:
                val = info["value"]
                lines.append(f"  {name.replace('_', ' ').title()}: ${val:,.2f}")
                context_used.append({"metric": name, "year": int(prior_year), "value": val})

        # Prior year estimated payments by quarter
        for q in range(1, 5):
            qname = f"estimated_payments_q{q}"
            info = prior.get(qname)
            if info and info.get("value") is not None:
                val = info["value"]
                lines.append(f"  Q{q} Estimated Payment: ${val:,.2f}")
                context_used.append({"metric": qname, "year": int(prior_year), "value": val})

        lines.append("")

    # Current year metrics (if available)
    current = metrics.get(current_year, {})
    if current:
        lines.append(f"TAX YEAR {current_year} (CURRENT YEAR — partial):")
        for name, info in sorted(current.items()):
            if info.get("value") is not None:
                val = info["value"]
                amended = " [AMENDED]" if info.get("amended") else ""
                lines.append(f"  {name.replace('_', ' ').title()}: ${val:,.2f}{amended}")
                context_used.append({"metric": name, "year": int(current_year), "value": val})
        lines.append("")

    # YoY comparison
    if prior and current:
        agi_prior = prior.get("adjusted_gross_income", {}).get("value")
        agi_current = current.get("adjusted_gross_income", {}).get("value")
        if agi_prior and agi_current and agi_prior != 0:
            pct = ((agi_current - agi_prior) / abs(agi_prior)) * 100
            lines.append(f"YoY AGI change: {pct:+.1f}%")
            lines.append("")

    # Prior quarter estimate amounts from thread
    if quarter > 1:
        lines.append(f"PRIOR QUARTERS ({current_year}):")
        for q in range(1, quarter):
            qname = f"estimated_payments_q{q}"
            info = current.get(qname)
            if info and info.get("value") is not None:
                lines.append(f"  Q{q} Payment: ${info['value']:,.2f}")
            else:
                lines.append(f"  Q{q} Payment: Not recorded")
        lines.append("")

    if not lines:
        return "No financial metrics available.", []

    return "\n".join(lines), context_used


def _build_system_prompt(quarter: int, tax_year: int, due_date: str) -> str:
    """Build the GPT-4o system prompt for quarterly estimate drafting."""
    return (
        f"You are drafting a quarterly estimated tax payment email for a CPA to send "
        f"to their client. This is Q{quarter} of {tax_year}. The payment is due "
        f"{due_date}.\n\n"
        "Draft a professional, personalized email that includes:\n"
        "1. Personal greeting referencing any recent life events or changes from "
        "the journal\n"
        "2. Estimate summary section — provide context the CPA can use to "
        "calculate/confirm the estimate amount (prior year tax, current year "
        "projections). Do NOT compute a specific tax amount — provide the data "
        "and suggest the CPA confirm.\n"
        "3. Changes since last quarter — reference any financial changes, document "
        "uploads, or strategy decisions since the last estimate email\n"
        "4. Open items — if there are unresolved questions from prior correspondence, "
        "list them with a polite follow-up request\n"
        "5. Action items — what the client needs to do (review estimate, make payment "
        f"by {due_date}, provide missing information)\n"
        "6. Next steps and upcoming deadlines\n\n"
        "Tone: professional but personal. Reference specific details from the "
        "context — names, amounts, dates. This should feel like it was written by "
        "a CPA who knows this client well, not a generic template.\n\n"
        "Return ONLY the email body text (no greeting like 'Hi Name,' and no "
        "sign-off — those are added by the template wrapper). No markdown formatting."
    )
