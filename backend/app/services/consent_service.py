"""
IRC Section 7216 consent tracking service.

Manages consent records for taxpayer authorization to disclose/use tax return
information through the AdvisoryBoard platform.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_consent import ClientConsent

logger = logging.getLogger(__name__)

# Document types that trigger consent requirements
TAX_DOCUMENT_TYPES = {"tax_return", "w2", "k1", "1099", "1040"}


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_consent_status(
    client_id: UUID,
    user_id: str,
    db: Session,
) -> dict[str, Any]:
    """
    Return the latest consent record for a client and computed status fields.

    Returns dict with: status, consent_date, expiration_date, is_expired,
    days_until_expiry, consent_record (or None).
    """
    record = (
        db.query(ClientConsent)
        .filter(
            ClientConsent.client_id == client_id,
            ClientConsent.user_id == user_id,
        )
        .order_by(ClientConsent.created_at.desc())
        .first()
    )

    if not record:
        return {
            "status": None,
            "consent_date": None,
            "expiration_date": None,
            "is_expired": False,
            "days_until_expiry": None,
            "consent_record": None,
        }

    now = datetime.now(timezone.utc)
    is_expired = (
        record.expiration_date is not None
        and record.expiration_date.astimezone(timezone.utc) < now
    )
    days_until_expiry = None
    if record.expiration_date and not is_expired:
        delta = record.expiration_date.astimezone(timezone.utc) - now
        days_until_expiry = delta.days

    return {
        "status": record.status,
        "consent_date": record.consent_date,
        "expiration_date": record.expiration_date,
        "is_expired": is_expired,
        "days_until_expiry": days_until_expiry,
        "consent_record": record,
    }


# ---------------------------------------------------------------------------
# Create / update
# ---------------------------------------------------------------------------


def create_or_update_consent(
    client_id: UUID,
    user_id: str,
    db: Session,
    *,
    consent_type: str,
    status: str,
    consent_date: Optional[datetime] = None,
    expiration_date: Optional[datetime] = None,
    consent_method: Optional[str] = None,
    taxpayer_name: Optional[str] = None,
    preparer_name: Optional[str] = None,
    preparer_firm: Optional[str] = None,
    notes: Optional[str] = None,
) -> ClientConsent:
    """
    Create a new consent record and sync the client's consent_status field.

    If status is 'obtained' and no expiration_date is given, defaults to
    consent_date + 1 year.
    """
    if status == "obtained" and consent_date and not expiration_date:
        expiration_date = consent_date + timedelta(days=365)

    record = ClientConsent(
        client_id=client_id,
        user_id=user_id,
        consent_type=consent_type,
        status=status,
        consent_date=consent_date,
        expiration_date=expiration_date,
        consent_method=consent_method,
        taxpayer_name=taxpayer_name,
        preparer_name=preparer_name,
        preparer_firm=preparer_firm,
        notes=notes,
    )
    db.add(record)

    # Sync the client-level status
    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        client.consent_status = status

    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Tax document detection hook
# ---------------------------------------------------------------------------


def check_tax_document_upload(
    client_id: UUID,
    document_type: Optional[str],
    db: Session,
) -> dict[str, Any]:
    """
    Called after document classification.  If the document is tax-related,
    sets has_tax_documents=True and flips consent_status from 'not_required'
    to 'pending'.
    """
    if not document_type or document_type.lower() not in TAX_DOCUMENT_TYPES:
        client = db.query(Client).filter(Client.id == client_id).first()
        return {
            "needs_consent": False,
            "consent_status": client.consent_status if client else "not_required",
        }

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"needs_consent": False, "consent_status": "not_required"}

    client.has_tax_documents = True
    if client.consent_status == "not_required":
        client.consent_status = "pending"

    db.commit()
    db.refresh(client)

    logger.info(
        "Tax document detected for client %s — consent_status=%s",
        client_id, client.consent_status,
    )

    return {
        "needs_consent": client.consent_status == "pending",
        "consent_status": client.consent_status,
    }


# ---------------------------------------------------------------------------
# Expiring consents
# ---------------------------------------------------------------------------


def get_expiring_consents(
    user_id: str,
    db: Session,
    days_ahead: int = 30,
) -> list[dict[str, Any]]:
    """
    Return clients whose most-recent consent expires within *days_ahead* days.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    # Get the latest consent per client for this user where status=obtained
    from sqlalchemy import func as sa_func

    subq = (
        db.query(
            ClientConsent.client_id,
            sa_func.max(ClientConsent.created_at).label("latest"),
        )
        .filter(
            ClientConsent.user_id == user_id,
            ClientConsent.status == "obtained",
        )
        .group_by(ClientConsent.client_id)
        .subquery()
    )

    records = (
        db.query(ClientConsent, Client.name)
        .join(
            subq,
            (ClientConsent.client_id == subq.c.client_id)
            & (ClientConsent.created_at == subq.c.latest),
        )
        .join(Client, Client.id == ClientConsent.client_id)
        .filter(
            ClientConsent.expiration_date.isnot(None),
            ClientConsent.expiration_date <= cutoff,
            ClientConsent.expiration_date > now,
        )
        .all()
    )

    results = []
    for consent, client_name in records:
        days_left = (consent.expiration_date.astimezone(timezone.utc) - now).days
        results.append({
            "client_id": consent.client_id,
            "client_name": client_name,
            "expiration_date": consent.expiration_date,
            "days_until_expiry": days_left,
            "consent_id": consent.id,
        })

    return results


# ---------------------------------------------------------------------------
# PDF consent form generation
# ---------------------------------------------------------------------------


def generate_consent_form_pdf(
    client_id: UUID,
    user_id: str,
    db: Session,
) -> tuple[bytes, str]:
    """
    Generate a professional IRC Section 7216 consent form PDF.

    Returns (pdf_bytes, storage_url).
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    from app.models.user import User
    from app.services import storage_service

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise ValueError("Client not found")

    user = db.query(User).filter(User.clerk_id == user_id).first()
    if not user:
        raise ValueError("User not found")

    taxpayer_name = client.name or ""
    preparer_name = " ".join(
        part for part in [user.first_name, user.last_name] if part
    ) or ""

    # Get latest consent record for pre-filling firm name
    latest = (
        db.query(ClientConsent)
        .filter(
            ClientConsent.client_id == client_id,
            ClientConsent.user_id == user_id,
        )
        .order_by(ClientConsent.created_at.desc())
        .first()
    )
    preparer_firm = (latest.preparer_firm if latest and latest.preparer_firm else "")

    # Build PDF
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ConsentTitle",
        parent=styles["Title"],
        fontSize=14,
        spaceAfter=6,
        alignment=1,  # center
    )
    subtitle_style = ParagraphStyle(
        "ConsentSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=12,
        alignment=1,
        textColor=colors.grey,
    )
    heading_style = ParagraphStyle(
        "ConsentHeading",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=12,
        spaceAfter=4,
        textColor=colors.HexColor("#1a1a1a"),
    )
    body_style = ParagraphStyle(
        "ConsentBody",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
        spaceAfter=8,
    )
    bold_body = ParagraphStyle(
        "ConsentBoldBody",
        parent=body_style,
        fontName="Helvetica-Bold",
    )
    small_style = ParagraphStyle(
        "ConsentSmall",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.grey,
    )
    sig_line_style = ParagraphStyle(
        "SigLine",
        parent=styles["Normal"],
        fontSize=9,
        spaceBefore=4,
        spaceAfter=2,
    )

    elements: list = []

    # Title
    elements.append(Paragraph(
        "CONSENT TO DISCLOSE TAX RETURN INFORMATION",
        title_style,
    ))
    elements.append(Paragraph(
        "IRC Section 7216 | Rev. Proc. 2013-14",
        subtitle_style,
    ))
    elements.append(Spacer(1, 6))

    # Required disclosure
    elements.append(Paragraph("REQUIRED DISCLOSURE", heading_style))
    elements.append(Paragraph(
        "Federal law requires this consent form be provided to you. Unless "
        "authorized by law, we cannot disclose your tax return information to "
        "third parties for purposes other than the preparation and filing of "
        "your tax return without your consent. If you consent to the disclosure "
        "of your tax return information, Federal law may not protect your tax "
        "return information from further use or distribution.",
        body_style,
    ))
    elements.append(Paragraph(
        "You are not required to complete this form to engage our tax return "
        "preparation services. If you do not sign this consent form, we will "
        "not disclose your tax return information to AdvisoryBoard Platform "
        "for the purposes described below.",
        body_style,
    ))
    elements.append(Spacer(1, 4))

    # Parties
    elements.append(Paragraph("PARTIES", heading_style))

    party_data = [
        ["Taxpayer Name:", taxpayer_name or "______________________________"],
        ["Taxpayer Identification\n(SSN / EIN):", "______________________________"],
        ["Tax Return Preparer:", preparer_name or "______________________________"],
        ["Preparer Firm Name:", preparer_firm or "______________________________"],
    ]
    party_table = Table(party_data, colWidths=[2 * inch, 4.5 * inch])
    party_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (1, 0), (1, -1), 0.5, colors.lightgrey),
    ]))
    elements.append(party_table)
    elements.append(Spacer(1, 8))

    # Purpose
    elements.append(Paragraph("PURPOSE OF DISCLOSURE AND USE", heading_style))
    elements.append(Paragraph(
        "To disclose and use your tax return information within the "
        "AdvisoryBoard document intelligence platform for the purposes of: "
        "AI-powered document analysis, automated action item extraction, "
        "client brief generation, and question-answering with source "
        "citations. Your tax return information will be processed by AI "
        "models (OpenAI, Anthropic, Google) to provide these services to "
        "your tax return preparer.",
        body_style,
    ))

    # Recipient
    elements.append(Paragraph("RECIPIENT", heading_style))
    elements.append(Paragraph(
        "AdvisoryBoard (myadvisoryboard.space), a cloud-based document "
        "intelligence platform.",
        body_style,
    ))

    # Duration
    elements.append(Paragraph("DURATION", heading_style))
    elements.append(Paragraph(
        "This consent is valid for one (1) year from the date of signature, "
        "unless you specify a different duration: ___________________________",
        body_style,
    ))
    elements.append(Spacer(1, 12))

    # Signature block
    elements.append(Paragraph("TAXPAYER SIGNATURE", heading_style))
    elements.append(Spacer(1, 20))

    sig_data = [
        ["_____________________________________________", "____________________"],
        ["Taxpayer Signature", "Date"],
        ["", ""],
        ["_____________________________________________", ""],
        ["Print Name", ""],
    ]
    sig_table = Table(sig_data, colWidths=[4.2 * inch, 2.3 * inch])
    sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("FONTSIZE", (0, 1), (-1, 1), 8),
        ("FONTSIZE", (0, 3), (-1, 3), 9.5),
        ("FONTSIZE", (0, 4), (-1, 4), 8),
        ("TEXTCOLOR", (0, 1), (-1, 1), colors.grey),
        ("TEXTCOLOR", (0, 4), (-1, 4), colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(sig_table)
    elements.append(Spacer(1, 16))

    # TIGTA notice
    elements.append(Paragraph(
        "If you believe your tax return information has been disclosed or "
        "used improperly in a manner unauthorized by law or without your "
        "permission, you may contact the Treasury Inspector General for Tax "
        "Administration (TIGTA) by telephone at 1-800-366-4484, or by email "
        "at complaints@tigta.treas.gov.",
        small_style,
    ))

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    buf.close()

    # Upload to Supabase Storage
    storage_path = f"consents/{user_id}/{client_id}/consent_form.pdf"
    storage_service.upload_file_to_path(
        storage_path, pdf_bytes, "application/pdf"
    )
    storage_url = storage_service.get_signed_url(storage_path, expires_in=3600)

    # Update form_generated_at on latest consent record
    if latest:
        latest.form_generated_at = datetime.now(timezone.utc)
        db.commit()

    logger.info(
        "Generated consent form PDF for client %s (%d bytes)",
        client_id, len(pdf_bytes),
    )

    return pdf_bytes, storage_url
