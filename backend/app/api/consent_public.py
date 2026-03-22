"""
Public consent signing endpoints — NO Clerk JWT auth required.

Auth is via the one-time signing token embedded in the email link.

Routes:
  GET  /api/consent/sign/{token}  — validate token, return form data
  POST /api/consent/sign/{token}  — complete the e-signature
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client_consent import ClientConsent
from app.services.consent_service import complete_signing, validate_signing_token

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SigningFormResponse(BaseModel):
    valid: bool
    client_name: Optional[str] = None
    preparer_name: Optional[str] = None
    preparer_firm: Optional[str] = None
    consent_purpose: str = "Use of tax return information within Callwen platform"
    expired: bool = False
    already_signed: bool = False


class SigningRequest(BaseModel):
    typed_name: str
    agreed: bool

    @field_validator("typed_name")
    @classmethod
    def name_min_length(cls, v: str) -> str:
        if len(v.strip()) < 2:
            raise ValueError("Typed name must be at least 2 characters")
        return v.strip()

    @field_validator("agreed")
    @classmethod
    def must_agree(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must agree to the consent terms")
        return v


class SigningResultResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_token(token: str, db: Session) -> tuple[ClientConsent | None, bool, bool]:
    """
    Look up the token and determine its state.

    Returns (consent_or_None, expired, already_signed).
    """
    from datetime import datetime, timezone

    record = (
        db.query(ClientConsent)
        .filter(ClientConsent.signing_token == token)
        .first()
    )
    if not record:
        return None, False, False

    if record.signed_at is not None:
        return None, False, True

    now = datetime.now(timezone.utc)
    if record.signing_token_expires_at and record.signing_token_expires_at.astimezone(timezone.utc) < now:
        return None, True, False

    return record, False, False


# ---------------------------------------------------------------------------
# GET /api/consent/sign/{token}
# ---------------------------------------------------------------------------


@router.get(
    "/sign/{token}",
    response_model=SigningFormResponse,
    summary="Validate a signing token and return form data",
)
async def get_signing_form(
    token: str,
    db: Session = Depends(get_db),
) -> SigningFormResponse:
    consent, expired, already_signed = _check_token(token, db)

    if consent is None:
        return SigningFormResponse(
            valid=False,
            expired=expired,
            already_signed=already_signed,
        )

    return SigningFormResponse(
        valid=True,
        client_name=consent.taxpayer_name,
        preparer_name=consent.preparer_name,
        preparer_firm=consent.preparer_firm,
    )


# ---------------------------------------------------------------------------
# POST /api/consent/sign/{token}
# ---------------------------------------------------------------------------


@router.post(
    "/sign/{token}",
    response_model=SigningResultResponse,
    summary="Complete the e-signature",
)
async def submit_signing(
    token: str,
    body: SigningRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SigningResultResponse:
    consent = validate_signing_token(token, db)
    if consent is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already-signed token",
        )

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")

    complete_signing(
        token=token,
        typed_name=body.typed_name,
        ip_address=ip_address,
        user_agent=user_agent,
        db=db,
    )

    return SigningResultResponse(
        success=True,
        message="Consent recorded successfully",
    )
