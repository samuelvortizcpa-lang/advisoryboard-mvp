"""
Client check-in API endpoints.

Two routers:
  checkin_router        — authenticated (Clerk JWT), template CRUD + send/retrieve
  checkin_public_router — public (token-based), form loading + submission
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.checkin_response import CheckinResponse as CheckinResponseModel
from app.models.checkin_template import CheckinTemplate
from app.models.organization import Organization
from app.models.user import User
from app.schemas.checkin import (
    CheckinQuestionSchema,
    CheckinResponseSchema,
    CheckinSendRequest,
    CheckinSubmitRequest,
    CheckinTemplateCreate,
    CheckinTemplateResponse,
    CheckinTemplateUpdate,
)
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services import checkin_service

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# Router 1: Authenticated endpoints
# ═══════════════════════════════════════════════════════════════════════════

checkin_router = APIRouter()


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@checkin_router.get(
    "/checkins/templates",
    response_model=List[CheckinTemplateResponse],
    summary="List available check-in templates",
)
async def list_templates(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[CheckinTemplateResponse]:
    templates = checkin_service.get_templates(db, auth.org_id)
    return [CheckinTemplateResponse.model_validate(t) for t in templates]


@checkin_router.post(
    "/checkins/templates",
    response_model=CheckinTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom check-in template",
)
async def create_template(
    body: CheckinTemplateCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> CheckinTemplateResponse:
    try:
        template = checkin_service.create_template(db, auth.org_id, auth.user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return CheckinTemplateResponse.model_validate(template)


@checkin_router.patch(
    "/checkins/templates/{template_id}",
    response_model=CheckinTemplateResponse,
    summary="Update a custom check-in template",
)
async def update_template(
    template_id: UUID,
    body: CheckinTemplateUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> CheckinTemplateResponse:
    try:
        template = checkin_service.update_template(db, template_id, auth.org_id, body)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return CheckinTemplateResponse.model_validate(template)


@checkin_router.delete(
    "/checkins/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a custom check-in template",
)
async def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    try:
        checkin_service.delete_template(db, template_id, auth.org_id)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ---------------------------------------------------------------------------
# Send check-in
# ---------------------------------------------------------------------------


@checkin_router.post(
    "/clients/{client_id}/checkins/send",
    response_model=CheckinResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Send a check-in questionnaire to a client",
)
async def send_checkin(
    client_id: UUID,
    body: CheckinSendRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> CheckinResponseSchema:
    check_client_access(auth, client_id, db)

    try:
        checkin = checkin_service.send_checkin(
            db=db,
            client_id=client_id,
            org_id=auth.org_id,
            user_id=auth.user_id,
            template_id=body.template_id,
            client_email=body.client_email,
            client_name=body.client_name,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # Attach template_name for response schema
    template = db.query(CheckinTemplate).filter(CheckinTemplate.id == checkin.template_id).first()
    return CheckinResponseSchema(
        **{
            "id": checkin.id,
            "client_id": checkin.client_id,
            "template_id": checkin.template_id,
            "template_name": template.name if template else "",
            "sent_by": checkin.sent_by,
            "sent_to_email": checkin.sent_to_email,
            "sent_to_name": checkin.sent_to_name,
            "access_token": checkin.access_token,
            "status": checkin.status,
            "responses": checkin.responses,
            "response_text": checkin.response_text,
            "completed_at": checkin.completed_at,
            "expires_at": checkin.expires_at,
            "sent_at": checkin.sent_at,
            "created_at": checkin.created_at,
        }
    )


# ---------------------------------------------------------------------------
# Retrieve check-ins
# ---------------------------------------------------------------------------


@checkin_router.get(
    "/clients/{client_id}/checkins",
    summary="List all check-ins for a client",
)
async def list_client_checkins(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[dict[str, Any]]:
    check_client_access(auth, client_id, db)
    return checkin_service.get_client_checkins(db, client_id, auth.org_id)


@checkin_router.get(
    "/checkins/{checkin_id}",
    summary="Get check-in detail with full Q&A",
)
async def get_checkin_detail(
    checkin_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict[str, Any]:
    detail = checkin_service.get_checkin_detail(db, checkin_id, auth.org_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Check-in not found")
    return detail


# ═══════════════════════════════════════════════════════════════════════════
# Router 2: Public endpoints (token-based, no auth)
# ═══════════════════════════════════════════════════════════════════════════

checkin_public_router = APIRouter()


class CheckinFormResponse(BaseModel):
    status: str
    questions: list[CheckinQuestionSchema] | None = None
    client_name: str | None = None
    firm_name: str | None = None
    template_name: str | None = None
    completed_at: datetime | None = None
    message: str | None = None


class CheckinSubmitResponse(BaseModel):
    status: str
    message: str


@checkin_public_router.get(
    "/{token}",
    response_model=CheckinFormResponse,
    summary="Load a check-in form by access token",
)
async def get_public_checkin(
    token: str,
    db: Session = Depends(get_db),
) -> CheckinFormResponse:
    checkin = (
        db.query(CheckinResponseModel)
        .filter(CheckinResponseModel.access_token == token)
        .first()
    )
    if checkin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Check-in not found")

    # Already completed
    if checkin.status == "completed":
        return CheckinFormResponse(
            status="completed",
            completed_at=checkin.completed_at,
            message="This check-in has already been submitted. Thank you!",
        )

    # Check expiry
    now = datetime.now(timezone.utc)
    expires_at = checkin.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        checkin.status = "expired"
        db.commit()
        return CheckinFormResponse(
            status="expired",
            message="This check-in link has expired. Please contact your advisor for a new link.",
        )

    # Pending — load template questions and context
    template = db.query(CheckinTemplate).filter(CheckinTemplate.id == checkin.template_id).first()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    # Resolve firm name: org name > sender name > generic
    firm_name: str | None = None
    if template.org_id:
        org = db.query(Organization).filter(Organization.id == template.org_id).first()
        if org:
            firm_name = org.name
    if not firm_name:
        sender = db.query(User).filter(User.clerk_id == checkin.sent_by).first()
        if sender:
            parts = [sender.first_name or "", sender.last_name or ""]
            firm_name = " ".join(p for p in parts if p).strip() or None

    questions = [CheckinQuestionSchema(**q) for q in template.questions]

    return CheckinFormResponse(
        status="pending",
        questions=questions,
        client_name=checkin.sent_to_name,
        firm_name=firm_name,
        template_name=template.name,
    )


@checkin_public_router.post(
    "/{token}/submit",
    response_model=CheckinSubmitResponse,
    summary="Submit check-in responses",
)
async def submit_public_checkin(
    token: str,
    body: CheckinSubmitRequest,
    db: Session = Depends(get_db),
) -> CheckinSubmitResponse:
    try:
        responses_data = [r.model_dump() for r in body.responses]
        await checkin_service.submit_checkin(db, token, responses_data)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Check-in not found")
    except ValueError as e:
        msg = str(e)
        if "expired" in msg.lower():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    return CheckinSubmitResponse(
        status="success",
        message="Thank you! Your responses have been sent to your advisor.",
    )
