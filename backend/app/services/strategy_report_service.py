"""
Strategy Impact Report PDF generation.

Generates a professional PDF showing a client's tax strategy
implementation, recommendations, and year-over-year comparison.
"""

from __future__ import annotations

import io
import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.organization import Organization
from app.models.tax_strategy import TaxStrategy
from app.models.user import User
from app.services.strategy_service import (
    PROFILE_FLAG_COLUMNS,
    _client_flags,
    _get_client_or_404,
    _strategy_applicable,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

NAVY = "#1B3A5C"
BLUE = "#2E75B6"
DARK = "#1a1a1a"
GRAY = "#6b7280"
LIGHT_GRAY = "#f3f4f6"

STATUS_DISPLAY = {
    "implemented": "Implemented",
    "recommended": "Recommended",
    "not_applicable": "N/A",
    "not_reviewed": "Not Reviewed",
    "declined": "Declined",
}

CATEGORY_LABELS = {
    "universal": "Universal Strategies",
    "business": "Business Strategies",
    "real_estate": "Real Estate Strategies",
    "high_income": "High Income Strategies",
    "estate": "Estate Planning Strategies",
    "medical": "Medical Professional Strategies",
}


def _fmt_money(n: float) -> str:
    if n >= 1_000_000:
        return f"${n / 1_000_000:,.1f}M"
    if n >= 1_000:
        return f"${n:,.0f}"
    return f"${n:,.2f}"


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------


def _gather_report_data(
    db: Session,
    client_id: UUID,
    user_id: str,
    tax_year: int,
    include_prior_years: bool,
) -> dict:
    """Gather all data needed for the report."""
    client = _get_client_or_404(db, client_id)
    flags = _client_flags(client)

    # Advisor info
    user = db.query(User).filter(User.clerk_id == user_id).first()
    advisor_name = "Advisor"
    if user:
        parts = [user.first_name, user.last_name]
        advisor_name = " ".join(p for p in parts if p) or user.email or "Advisor"

    # Org / firm name
    firm_name = None
    if client.org_id:
        org = db.query(Organization).filter(Organization.id == client.org_id).first()
        if org:
            firm_name = org.name

    # All active strategies
    all_strategies = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .order_by(TaxStrategy.category, TaxStrategy.display_order)
        .all()
    )
    applicable = [
        s for s in all_strategies
        if _strategy_applicable(flags, s.required_flags or [])
    ]

    # Current year statuses
    current_statuses = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id == client_id,
            ClientStrategyStatus.tax_year == tax_year,
        )
        .all()
    )
    status_map = {s.strategy_id: s for s in current_statuses}

    # Build strategy details
    implemented = []
    recommended = []
    total_impact = 0.0
    total_reviewed = 0

    for strat in applicable:
        entry = status_map.get(strat.id)
        s_status = entry.status if entry else "not_reviewed"
        s_notes = entry.notes if entry else None
        s_impact = float(entry.estimated_impact) if entry and entry.estimated_impact else None

        if s_status != "not_reviewed":
            total_reviewed += 1
        if s_impact:
            total_impact += s_impact

        item = {
            "name": strat.name,
            "category": strat.category,
            "description": strat.description,
            "status": s_status,
            "notes": s_notes,
            "estimated_impact": s_impact,
        }
        if s_status == "implemented":
            implemented.append(item)
        elif s_status == "recommended":
            recommended.append(item)

    # Prior years
    prior_years_data = {}
    if include_prior_years:
        for yr in range(tax_year - 3, tax_year):
            yr_statuses = (
                db.query(ClientStrategyStatus)
                .filter(
                    ClientStrategyStatus.client_id == client_id,
                    ClientStrategyStatus.tax_year == yr,
                )
                .all()
            )
            if yr_statuses:
                prior_years_data[yr] = {s.strategy_id: s for s in yr_statuses}

    return {
        "client": client,
        "advisor_name": advisor_name,
        "firm_name": firm_name,
        "tax_year": tax_year,
        "applicable": applicable,
        "implemented": implemented,
        "recommended": recommended,
        "total_impact": total_impact,
        "total_reviewed": total_reviewed,
        "total_applicable": len(applicable),
        "status_map": status_map,
        "prior_years_data": prior_years_data,
    }


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------


def generate_strategy_report(
    db: Session,
    client_id: UUID,
    user_id: str,
    tax_year: Optional[int] = None,
    include_prior_years: bool = True,
) -> bytes:
    """Generate a professional PDF strategy impact report."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    year = tax_year if tax_year is not None else date.today().year
    data = _gather_report_data(db, client_id, user_id, year, include_prior_years)

    client = data["client"]
    client_name = client.name or "Client"
    advisor_name = data["advisor_name"]
    firm_name = data["firm_name"]
    header_name = firm_name or f"Prepared by {advisor_name}"

    buf = io.BytesIO()

    # Footer callback
    footer_text = f"Confidential — Prepared by {firm_name or advisor_name} for {client_name}"

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawString(
            inch, 0.5 * inch,
            f"{footer_text} — Page {doc.page}",
        )
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=0.75 * inch,
    )

    # ── Styles ────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    s_firm = ParagraphStyle(
        "Firm",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor(GRAY),
        spaceAfter=4,
    )
    s_title = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor(NAVY),
        spaceAfter=6,
        leading=26,
    )
    s_subtitle = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=13,
        textColor=colors.HexColor(BLUE),
        spaceAfter=4,
    )
    s_date = ParagraphStyle(
        "ReportDate",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor(GRAY),
        spaceAfter=24,
    )
    s_section = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor(NAVY),
        spaceBefore=16,
        spaceAfter=10,
        fontName="Helvetica-Bold",
    )
    s_body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9.5,
        textColor=colors.HexColor(DARK),
        leading=13,
        spaceAfter=4,
    )
    s_bold = ParagraphStyle(
        "BodyBold",
        parent=s_body,
        fontName="Helvetica-Bold",
        spaceAfter=2,
    )
    s_notes = ParagraphStyle(
        "Notes",
        parent=s_body,
        textColor=colors.HexColor(GRAY),
        fontName="Helvetica-Oblique",
        leftIndent=12,
    )
    s_metric_label = ParagraphStyle(
        "MetricLabel",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor(GRAY),
    )
    s_metric_value = ParagraphStyle(
        "MetricValue",
        parent=styles["Normal"],
        fontSize=16,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor(NAVY),
    )

    elements: list = []

    # ── Page 1 — Cover / Summary ─────────────────────────────────────
    elements.append(Spacer(1, 0.5 * inch))
    elements.append(Paragraph(header_name, s_firm))
    elements.append(Paragraph(f"Tax Strategy Review — {year}", s_title))
    elements.append(Paragraph(f"Prepared for {client_name}", s_subtitle))
    if client.business_name:
        elements.append(Paragraph(client.business_name, s_body))
    elements.append(Paragraph(date.today().strftime("%B %d, %Y"), s_date))

    # Summary metrics box
    coverage = (
        round(len(data["implemented"]) / data["total_applicable"] * 100)
        if data["total_applicable"] > 0 else 0
    )
    metrics = [
        ["Strategies Implemented", str(len(data["implemented"]))],
        ["Estimated Tax Impact", _fmt_money(data["total_impact"]) if data["total_impact"] > 0 else "—"],
        ["Strategies Reviewed", f"{data['total_reviewed']} of {data['total_applicable']}"],
        ["Coverage", f"{coverage}%"],
    ]

    metric_cells = []
    for label, value in metrics:
        metric_cells.append([
            Paragraph(value, s_metric_value),
            Paragraph(label, s_metric_label),
        ])

    metric_table = Table(
        [metric_cells],
        colWidths=[doc.width / 4] * 4,
    )
    metric_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(LIGHT_GRAY)),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    elements.append(metric_table)

    # ── Page 2 — Implemented Strategies ──────────────────────────────
    elements.append(PageBreak())
    elements.append(Paragraph(f"Implemented Tax Strategies — {year}", s_section))

    if data["implemented"]:
        impl_total = 0.0
        for item in data["implemented"]:
            elements.append(Paragraph(item["name"], s_bold))
            if item["description"]:
                elements.append(Paragraph(item["description"], s_body))
            impact_str = _fmt_money(item["estimated_impact"]) if item["estimated_impact"] else "—"
            elements.append(Paragraph(f"Estimated Impact: {impact_str}", s_body))
            if item["notes"]:
                elements.append(Paragraph(f"Notes: {item['notes']}", s_notes))
            if item["estimated_impact"]:
                impl_total += item["estimated_impact"]
            elements.append(Spacer(1, 8))

        if impl_total > 0:
            elements.append(Spacer(1, 4))
            total_style = ParagraphStyle(
                "TotalImpact",
                parent=s_bold,
                fontSize=11,
                textColor=colors.HexColor(BLUE),
            )
            elements.append(Paragraph(
                f"Total Estimated Impact: {_fmt_money(impl_total)}",
                total_style,
            ))
    else:
        elements.append(Paragraph(
            "No strategies marked as implemented for this tax year.",
            s_body,
        ))

    # ── Page 3 — Recommendations ─────────────────────────────────────
    elements.append(PageBreak())
    elements.append(Paragraph(f"Recommended Strategies for {year + 1}", s_section))

    if data["recommended"]:
        for item in data["recommended"]:
            elements.append(Paragraph(item["name"], s_bold))
            if item["description"]:
                elements.append(Paragraph(item["description"], s_body))
            if item["notes"]:
                elements.append(Paragraph(f"Notes: {item['notes']}", s_notes))
            elements.append(Spacer(1, 8))
    else:
        elements.append(Paragraph(
            "All applicable strategies have been reviewed.",
            s_body,
        ))

    # ── Page 4 — Year-Over-Year Comparison ───────────────────────────
    prior = data["prior_years_data"]
    if include_prior_years and prior:
        elements.append(PageBreak())

        all_years = sorted(prior.keys()) + [year]
        elements.append(Paragraph(
            f"Strategy Evolution — {all_years[0]} to {all_years[-1]}",
            s_section,
        ))

        # Build table: header row + strategy rows + summary row
        header_row = ["Strategy"] + [str(y) for y in all_years]
        table_data = [header_row]

        year_impl_counts = {y: 0 for y in all_years}
        year_impact_totals = {y: 0.0 for y in all_years}

        for strat in data["applicable"]:
            row = [Paragraph(strat.name, s_body)]
            for yr in all_years:
                if yr == year:
                    entry = data["status_map"].get(strat.id)
                else:
                    yr_map = prior.get(yr, {})
                    entry = yr_map.get(strat.id)

                if entry:
                    status_text = STATUS_DISPLAY.get(entry.status, entry.status)
                    if entry.status == "implemented":
                        year_impl_counts[yr] += 1
                    if entry.estimated_impact:
                        year_impact_totals[yr] += float(entry.estimated_impact)
                else:
                    status_text = "—"

                row.append(Paragraph(status_text, s_body))
            table_data.append(row)

        # Summary row
        summary_row = [Paragraph("<b>Implemented</b>", s_body)]
        for yr in all_years:
            summary_row.append(Paragraph(f"<b>{year_impl_counts[yr]}</b>", s_body))
        table_data.append(summary_row)

        impact_row = [Paragraph("<b>Est. Impact</b>", s_body)]
        for yr in all_years:
            val = year_impact_totals[yr]
            impact_row.append(Paragraph(
                f"<b>{_fmt_money(val)}</b>" if val > 0 else "—",
                s_body,
            ))
        table_data.append(impact_row)

        # Column widths
        n_cols = len(all_years) + 1
        name_width = 2.5 * inch
        year_width = (doc.width - name_width) / len(all_years)
        col_widths = [name_width] + [year_width] * len(all_years)

        comparison_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        comparison_table.setStyle(TableStyle([
            # Header
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(NAVY)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(LIGHT_GRAY)),
            # Body
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            # Grid
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor(NAVY)),
            ("LINEBELOW", (0, 1), (-1, -3), 0.25, colors.lightgrey),
            # Summary rows
            ("LINEABOVE", (0, -2), (-1, -2), 0.75, colors.HexColor(NAVY)),
            ("BACKGROUND", (0, -2), (-1, -1), colors.HexColor(LIGHT_GRAY)),
            # Alternating row shading
            *[
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f9fafb"))
                for i in range(2, len(table_data) - 2, 2)
            ],
        ]))
        elements.append(comparison_table)

    # Build PDF
    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
