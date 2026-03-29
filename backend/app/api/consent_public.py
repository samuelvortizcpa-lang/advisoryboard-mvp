"""
Public consent signing endpoints — NO Clerk JWT auth required.

Auth is via the one-time signing token embedded in the email link.

Routes:
  GET  /api/consent/sign/{token}  — validate token, return form data
  POST /api/consent/sign/{token}  — complete the e-signature
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client_consent import ClientConsent
from app.services.consent_service import complete_signing, validate_signing_token

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# ---------------------------------------------------------------------------
# Failed token lookup tracker (anti-enumeration)
# ---------------------------------------------------------------------------
_FAILED_WINDOW = 600  # 10 minutes
_FAILED_MAX = 5

_failed_lookups: dict[str, list[float]] = defaultdict(list)


def _check_enumeration_block(ip: str) -> None:
    """Block IPs with too many failed token lookups."""
    now = time.monotonic()
    timestamps = _failed_lookups.get(ip)
    if not timestamps:
        return
    # Prune old entries
    fresh = [t for t in timestamps if now - t < _FAILED_WINDOW]
    if fresh:
        _failed_lookups[ip] = fresh
    else:
        del _failed_lookups[ip]
        return
    if len(fresh) >= _FAILED_MAX:
        logger.warning("Token enumeration blocked for IP %s (%d failures)", ip, len(fresh))
        raise HTTPException(status_code=429, detail="Too many failed attempts")


def _record_failed_lookup(ip: str) -> None:
    """Record a failed token lookup for enumeration tracking."""
    _failed_lookups[ip].append(time.monotonic())


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
@limiter.limit("10/minute")
async def get_signing_form(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
) -> SigningFormResponse:
    ip = request.client.host if request.client else "unknown"
    _check_enumeration_block(ip)

    consent, expired, already_signed = _check_token(token, db)

    if consent is None:
        if not expired and not already_signed:
            # Token not found at all — potential enumeration
            _record_failed_lookup(ip)
            logger.info("Failed token lookup from %s", ip)
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
@limiter.limit("5/minute")
async def submit_signing(
    request: Request,
    token: str,
    body: SigningRequest,
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
