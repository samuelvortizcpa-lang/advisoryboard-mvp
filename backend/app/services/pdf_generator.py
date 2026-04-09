"""
Server-side PDF generation using WeasyPrint.

Two public functions:
  - generate_brief_pdf()   — client meeting brief
  - generate_chat_response_pdf() — single chat Q&A response
"""

from __future__ import annotations

import logging
from datetime import datetime

import markdown
from weasyprint import HTML

logger = logging.getLogger(__name__)

# ── Shared CSS ──────────────────────────────────────────────────────────────────

_BASE_CSS = """
@page {
    size: A4;
    margin: 2cm 2.5cm;
    @bottom-center {
        content: counter(page) " of " counter(pages);
        font-size: 9px;
        color: #94a3b8;
    }
}
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
    line-height: 1.6;
    color: #1e293b;
}
h1 {
    font-size: 22px;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 8px;
    margin-bottom: 16px;
    color: #0f172a;
}
h2 {
    font-size: 16px;
    margin-top: 24px;
    margin-bottom: 8px;
    color: #1e40af;
}
h3 {
    font-size: 14px;
    margin-top: 16px;
    margin-bottom: 6px;
    color: #334155;
}
p { margin: 8px 0; }
ul, ol { padding-left: 20px; }
li { margin: 4px 0; }
strong { font-weight: 600; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 16px 0; }
.meta {
    font-size: 11px;
    color: #64748b;
    margin-bottom: 20px;
}
.question-box {
    background: #eff6ff;
    border-left: 4px solid #2563eb;
    padding: 12px 16px;
    margin-bottom: 20px;
    border-radius: 0 8px 8px 0;
}
.question-box .label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #64748b;
    margin-bottom: 4px;
}
.question-box .text {
    font-size: 14px;
    font-weight: 500;
    color: #1e40af;
}
.sources {
    margin-top: 24px;
    padding-top: 12px;
    border-top: 1px solid #e2e8f0;
}
.sources h3 {
    font-size: 12px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.source-item {
    font-size: 11px;
    color: #475569;
    padding: 4px 0;
}
.confidence {
    display: inline-block;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    margin-bottom: 16px;
}
.confidence-high { background: #dcfce7; color: #166534; }
.confidence-medium { background: #fef9c3; color: #854d0e; }
.confidence-low { background: #fee2e2; color: #991b1b; }
"""


def _md_to_html(md_content: str) -> str:
    """Convert markdown to HTML with common extensions."""
    return markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "nl2br"],
    )


def generate_brief_pdf(
    markdown_content: str,
    client_name: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    """Render a client meeting brief markdown string to a styled PDF."""
    generated_at = generated_at or datetime.utcnow()
    date_str = generated_at.strftime("%B %d, %Y at %I:%M %p")
    title = f"Client Brief — {client_name}" if client_name else "Client Meeting Brief"

    body_html = _md_to_html(markdown_content)

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>{_BASE_CSS}</style>
</head>
<body>
    <h1>{title}</h1>
    <div class="meta">Generated on {date_str}</div>
    {body_html}
</body>
</html>"""

    pdf_bytes: bytes = HTML(string=html_doc).write_pdf()
    logger.info("Generated brief PDF (%d bytes) for %s", len(pdf_bytes), client_name or "unknown")
    return pdf_bytes


def generate_chat_response_pdf(
    question: str,
    answer_markdown: str,
    sources: list[dict] | None = None,
    client_name: str | None = None,
    confidence: str | None = None,
    model_used: str | None = None,
) -> bytes:
    """Render a single chat Q&A exchange to a styled PDF."""
    title = f"AI Response — {client_name}" if client_name else "AI Response"

    confidence_html = ""
    if confidence:
        css_class = f"confidence-{confidence}" if confidence in ("high", "medium", "low") else ""
        confidence_html = f'<span class="confidence {css_class}">{confidence.title()} confidence</span>'

    answer_html = _md_to_html(answer_markdown)

    sources_html = ""
    if sources:
        items = ""
        for src in sources:
            fname = src.get("filename", "Unknown")
            preview = src.get("preview") or src.get("chunk_text") or ""
            if len(preview) > 150:
                preview = preview[:150] + "…"
            items += f'<div class="source-item"><strong>{fname}</strong> — {preview}</div>'
        sources_html = f"""
        <div class="sources">
            <h3>Sources</h3>
            {items}
        </div>"""

    model_line = f" · Model: {model_used}" if model_used else ""
    date_str = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p")

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>{_BASE_CSS}</style>
</head>
<body>
    <h1>{title}</h1>
    <div class="meta">Exported on {date_str}{model_line}</div>
    {confidence_html}
    <div class="question-box">
        <div class="label">Question</div>
        <div class="text">{question}</div>
    </div>
    {answer_html}
    {sources_html}
</body>
</html>"""

    pdf_bytes: bytes = HTML(string=html_doc).write_pdf()
    logger.info("Generated chat PDF (%d bytes)", len(pdf_bytes))
    return pdf_bytes
