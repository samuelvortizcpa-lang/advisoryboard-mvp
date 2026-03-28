"""
Client Brief API endpoints.

Routes (all require Clerk JWT auth):
  POST /api/clients/{client_id}/briefs/generate
  GET  /api/clients/{client_id}/briefs/latest
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client_brief import ClientBrief
from app.services.auth_context import AuthContext, check_client_access, get_auth

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas (local, route-level)
# ---------------------------------------------------------------------------


class BriefResponse(BaseModel):
    id: str
    client_id: str
    content: str
    generated_at: datetime
    document_count: Optional[int] = None
    action_item_count: Optional[int] = None
    metadata_: Optional[dict] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# POST — Generate a new brief
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/briefs/generate",
    response_model=BriefResponse,
    summary="Generate a meeting prep brief for a client",
)
async def generate_brief(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> BriefResponse:
    check_client_access(auth, client_id, db)

    from app.services.brief_generator import generate_brief as _generate

    try:
        result = await _generate(db, client_id=client_id, user_id=auth.user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Persist the brief
    brief = ClientBrief(
        client_id=client_id,
        user_id=auth.user_id,
        content=result["content"],
        document_count=result["document_count"],
        action_item_count=result["action_item_count"],
        metadata_=result["metadata"],
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)

    return BriefResponse(
        id=str(brief.id),
        client_id=str(brief.client_id),
        content=brief.content,
        generated_at=brief.generated_at,
        document_count=brief.document_count,
        action_item_count=brief.action_item_count,
        metadata_=brief.metadata_,
    )


# ---------------------------------------------------------------------------
# GET — Fetch the latest brief
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/briefs/latest",
    response_model=Optional[BriefResponse],
    summary="Get the most recent brief for a client",
)
async def get_latest_brief(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> Optional[BriefResponse]:
    check_client_access(auth, client_id, db)

    brief = (
        db.query(ClientBrief)
        .filter(ClientBrief.client_id == client_id)
        .order_by(ClientBrief.generated_at.desc())
        .first()
    )

    if brief is None:
        return None

    return BriefResponse(
        id=str(brief.id),
        client_id=str(brief.client_id),
        content=brief.content,
        generated_at=brief.generated_at,
        document_count=brief.document_count,
        action_item_count=brief.action_item_count,
        metadata_=brief.metadata_,
    )
