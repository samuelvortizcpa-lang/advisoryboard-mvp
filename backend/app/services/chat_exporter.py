"""
Chat history export utilities.

Functions:
  export_chat_as_txt(client_id, client_name, db) -> str
  export_chat_as_pdf(client_id, client_name, db) -> bytes
"""

import io
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_messages(db: Session, client_id: UUID) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.client_id == client_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%B %d, %Y at %I:%M %p")


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# TXT export
# ---------------------------------------------------------------------------


def export_chat_as_txt(client_id: UUID, client_name: str, db: Session) -> str:
    messages = _get_messages(db, client_id)

    lines = [
        "==========================================",
        "Callwen Chat History",
        f"Client: {client_name}",
        f"Export Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}",
        f"Total Messages: {len(messages)}",
        "==========================================",
        "",
    ]

    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.role == "user":
            lines.append(f"[{_fmt_ts(msg.created_at)}]")
            lines.append(f"Q: {msg.content}")
            lines.append("")
            if i + 1 < len(messages) and messages[i + 1].role == "assistant":
                reply = messages[i + 1]
                lines.append(f"A: {reply.content}")
                if reply.sources:
                    lines.append("Sources:")
                    for src in reply.sources:
                        lines.append(f"  * {src['filename']}")
                lines.append("")
                i += 2
                continue
        i += 1

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------


def export_chat_as_pdf(client_id: UUID, client_name: str, db: Session) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

    messages = _get_messages(db, client_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ABTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1e40af"),
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "ABMeta",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=2,
    )
    timestamp_style = ParagraphStyle(
        "ABTimestamp",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#9ca3af"),
        spaceBefore=14,
        spaceAfter=4,
    )
    question_style = ParagraphStyle(
        "ABQuestion",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#111827"),
        leftIndent=12,
        spaceAfter=6,
        leading=14,
    )
    answer_style = ParagraphStyle(
        "ABAnswer",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#374151"),
        leftIndent=12,
        spaceAfter=4,
        leading=14,
    )
    source_style = ParagraphStyle(
        "ABSource",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#6b7280"),
        leftIndent=24,
        spaceAfter=2,
    )

    story = []

    # Header
    story.append(Paragraph("Callwen Chat History", title_style))
    story.append(Paragraph(f"Client: {client_name}", meta_style))
    story.append(
        Paragraph(
            f"Export Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}"
            f"&nbsp;&nbsp;·&nbsp;&nbsp;{len(messages)} messages",
            meta_style,
        )
    )
    story.append(Spacer(1, 0.15 * inch))
    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb"))
    )
    story.append(Spacer(1, 0.05 * inch))

    if not messages:
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("No chat messages found.", styles["Normal"]))
    else:
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.role == "user":
                story.append(Paragraph(_fmt_ts(msg.created_at), timestamp_style))
                story.append(
                    Paragraph(f"<b>Q:</b> {_escape_html(msg.content)}", question_style)
                )
                if i + 1 < len(messages) and messages[i + 1].role == "assistant":
                    reply = messages[i + 1]
                    story.append(
                        Paragraph(
                            f"<b>A:</b> {_escape_html(reply.content)}", answer_style
                        )
                    )
                    if reply.sources:
                        story.append(Paragraph("Sources:", source_style))
                        for src in reply.sources:
                            story.append(
                                Paragraph(
                                    f"&nbsp;&nbsp;• {_escape_html(src['filename'])}",
                                    source_style,
                                )
                            )
                    story.append(
                        HRFlowable(
                            width="100%",
                            thickness=0.5,
                            color=colors.HexColor("#f3f4f6"),
                        )
                    )
                    i += 2
                    continue
            i += 1

    doc.build(story)
    return buffer.getvalue()
