"""
IRC Section 7216 consent tracking API endpoints.

Routes (all require Clerk JWT auth + client ownership):
  GET  /api/clients/{client_id}/consent               — current consent status
  POST /api/clients/{client_id}/consent               — create/update consent
  POST /api/clients/{client_id}/consent/generate-form  — generate PDF form
  GET  /api/clients/{client_id}/consent/history        — all consent records
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.client import Client
from app.services import user_service
from app.services.consent_service import (
    create_or_update_consent,
    generate_consent_form_pdf,
    get_consent_status,
    send_consent_for_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ConsentResponse(BaseModel):
    id: UUID
    client_id: UUID
    user_id: str
    consent_type: str
    status: str
    consent_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    consent_method: Optional[str] = None
    taxpayer_name: Optional[str] = None
    preparer_name: Optional[str] = None
    preparer_firm: Optional[str] = None
    notes: Optional[str] = None
    form_generated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConsentCreateRequest(BaseModel):
    consent_type: str
    status: str
    consent_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    consent_method: Optional[str] = None
    taxpayer_name: Optional[str] = None
    preparer_name: Optional[str] = None
    preparer_firm: Optional[str] = None
    notes: Optional[str] = None


class ConsentStatusResponse(BaseModel):
    consent_status: str
    has_tax_documents: bool
    latest_consent: Optional[ConsentResponse] = None
    is_expired: bool
    days_until_expiry: Optional[int] = None


class GenerateFormJsonResponse(BaseModel):
    storage_url: str
    form_generated_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_client_ownership(db: Session, client_id: UUID, owner_id: UUID) -> Client:
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner_id)
        .first()
    )
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client not found"
        )
    return client


# ---------------------------------------------------------------------------
# GET /api/clients/{client_id}/consent
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/consent",
    response_model=ConsentStatusResponse,
    summary="Get current consent status for a client",
)
async def get_client_consent(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ConsentStatusResponse:
    user = user_service.get_or_create_user(db, current_user)
    client = _verify_client_ownership(db, client_id, user.id)

    info = get_consent_status(client_id, user.clerk_id, db)

    latest_consent = None
    if info["consent_record"]:
        latest_consent = ConsentResponse.model_validate(info["consent_record"])

    return ConsentStatusResponse(
        consent_status=client.consent_status,
        has_tax_documents=client.has_tax_documents,
        latest_consent=latest_consent,
        is_expired=info["is_expired"],
        days_until_expiry=info["days_until_expiry"],
    )


# ---------------------------------------------------------------------------
# POST /api/clients/{client_id}/consent
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/consent",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a consent record",
)
async def create_consent(
    client_id: UUID,
    body: ConsentCreateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ConsentResponse:
    user = user_service.get_or_create_user(db, current_user)
    _verify_client_ownership(db, client_id, user.id)

    record = create_or_update_consent(
        client_id,
        user.clerk_id,
        db,
        consent_type=body.consent_type,
        status=body.status,
        consent_date=body.consent_date,
        expiration_date=body.expiration_date,
        consent_method=body.consent_method,
        taxpayer_name=body.taxpayer_name,
        preparer_name=body.preparer_name,
        preparer_firm=body.preparer_firm,
        notes=body.notes,
    )

    return ConsentResponse.model_validate(record)


# ---------------------------------------------------------------------------
# POST /api/clients/{client_id}/consent/generate-form
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/consent/generate-form",
    summary="Generate a Section 7216 consent form PDF",
)
async def generate_form(
    client_id: UUID,
    format: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    user = user_service.get_or_create_user(db, current_user)
    client = _verify_client_ownership(db, client_id, user.id)

    pdf_bytes, storage_url = generate_consent_form_pdf(
        client_id, user.clerk_id, db,
    )

    if format == "json":
        return GenerateFormJsonResponse(
            storage_url=storage_url,
            form_generated_at=datetime.utcnow(),
        )

    safe_name = (client.name or "client").replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="7216_consent_{safe_name}.pdf"'
        },
    )


# ---------------------------------------------------------------------------
# GET /api/clients/{client_id}/consent/history
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/consent/history",
    response_model=List[ConsentResponse],
    summary="List all consent records for a client",
)
async def consent_history(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[ConsentResponse]:
    user = user_service.get_or_create_user(db, current_user)
    _verify_client_ownership(db, client_id, user.id)

    from app.models.client_consent import ClientConsent

    records = (
        db.query(ClientConsent)
        .filter(
            ClientConsent.client_id == client_id,
            ClientConsent.user_id == user.clerk_id,
        )
        .order_by(ClientConsent.created_at.desc())
        .all()
    )

    return [ConsentResponse.model_validate(r) for r in records]


# ---------------------------------------------------------------------------
# POST /api/clients/{client_id}/consent/send-for-signature
# ---------------------------------------------------------------------------


class SendForSignatureRequest(BaseModel):
    taxpayer_email: str
    taxpayer_name: str
    preparer_name: str
    preparer_firm: Optional[str] = None


class SendForSignatureResponse(BaseModel):
    success: bool
    consent_id: UUID
    message: str


@router.post(
    "/clients/{client_id}/consent/send-for-signature",
    response_model=SendForSignatureResponse,
    summary="Send a consent form for e-signature via email",
)
async def send_for_signature(
    client_id: UUID,
    body: SendForSignatureRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> SendForSignatureResponse:
    user = user_service.get_or_create_user(db, current_user)
    _verify_client_ownership(db, client_id, user.id)

    consent = send_consent_for_signature(
        client_id=client_id,
        user_id=user.clerk_id,
        taxpayer_email=body.taxpayer_email,
        taxpayer_name=body.taxpayer_name,
        preparer_name=body.preparer_name,
        preparer_firm=body.preparer_firm,
        db=db,
    )

    return SendForSignatureResponse(
        success=True,
        consent_id=consent.id,
        message=f"Consent request sent to {body.taxpayer_email}",
    )
