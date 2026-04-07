"""Engagement management API — templates, client assignments, and task generation."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.client_engagement import ClientEngagement
from app.models.engagement_template import EngagementTemplate
from app.schemas.engagement import (
    AssignEngagementRequest,
    ClientEngagementResponse,
    CreateTemplateRequest,
    EngagementTemplateResponse,
    GenerateTasksResponse,
    UpdateEngagementRequest,
)
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.engagement_engine import (
    assign_engagement,
    generate_upcoming_tasks,
    remove_engagement,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /engagement-templates
# ---------------------------------------------------------------------------

@router.get(
    "/engagement-templates",
    response_model=list[EngagementTemplateResponse],
    summary="List all active engagement templates",
)
async def list_templates(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[EngagementTemplateResponse]:
    rows = (
        db.query(EngagementTemplate)
        .options(joinedload(EngagementTemplate.tasks))
        .filter(EngagementTemplate.is_active == True)  # noqa: E712
        .order_by(EngagementTemplate.name)
        .all()
    )
    return [EngagementTemplateResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# POST /engagement-templates
# ---------------------------------------------------------------------------

@router.post(
    "/engagement-templates",
    response_model=EngagementTemplateResponse,
    status_code=201,
    summary="Create a custom engagement template",
)
async def create_template(
    body: CreateTemplateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> EngagementTemplateResponse:
    template = EngagementTemplate(
        name=body.name,
        description=body.description,
        entity_types=body.entity_types,
        is_system=False,
        created_by=auth.user_id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return EngagementTemplateResponse.model_validate(template)


# ---------------------------------------------------------------------------
# GET /clients/{client_id}/engagements
# ---------------------------------------------------------------------------

@router.get(
    "/clients/{client_id}/engagements",
    response_model=list[ClientEngagementResponse],
    summary="List engagements for a client",
)
async def list_client_engagements(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[ClientEngagementResponse]:
    check_client_access(auth, client_id, db)
    rows = (
        db.query(ClientEngagement)
        .options(
            joinedload(ClientEngagement.template).joinedload(EngagementTemplate.tasks),
        )
        .filter(ClientEngagement.client_id == client_id)
        .order_by(ClientEngagement.created_at.desc())
        .all()
    )
    return [ClientEngagementResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# POST /clients/{client_id}/engagements
# ---------------------------------------------------------------------------

@router.post(
    "/clients/{client_id}/engagements",
    response_model=ClientEngagementResponse,
    status_code=201,
    summary="Assign engagement template to client",
)
async def assign_client_engagement(
    client_id: UUID,
    body: AssignEngagementRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientEngagementResponse:
    check_client_access(auth, client_id, db)

    # Verify template exists
    template = db.query(EngagementTemplate).filter(EngagementTemplate.id == body.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Engagement template not found")

    # Check for existing assignment
    existing = (
        db.query(ClientEngagement)
        .filter(
            ClientEngagement.client_id == client_id,
            ClientEngagement.template_id == body.template_id,
        )
        .first()
    )
    if existing:
        if existing.is_active:
            raise HTTPException(status_code=409, detail="This engagement is already assigned")
        # Reactivate
        existing.is_active = True
        existing.start_year = body.start_year or existing.start_year
        existing.custom_overrides = body.custom_overrides
        db.commit()
        db.refresh(existing)
        # Load template relationship
        engagement = (
            db.query(ClientEngagement)
            .options(joinedload(ClientEngagement.template).joinedload(EngagementTemplate.tasks))
            .filter(ClientEngagement.id == existing.id)
            .first()
        )
        return ClientEngagementResponse.model_validate(engagement)

    engagement = assign_engagement(
        db,
        client_id=client_id,
        template_id=body.template_id,
        user_id=auth.user_id,
        start_year=body.start_year,
        custom_overrides=body.custom_overrides,
    )

    # Reload with relationships
    engagement = (
        db.query(ClientEngagement)
        .options(joinedload(ClientEngagement.template).joinedload(EngagementTemplate.tasks))
        .filter(ClientEngagement.id == engagement.id)
        .first()
    )
    return ClientEngagementResponse.model_validate(engagement)


# ---------------------------------------------------------------------------
# DELETE /clients/{client_id}/engagements/{engagement_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/clients/{client_id}/engagements/{engagement_id}",
    status_code=204,
    summary="Remove engagement from client",
)
async def remove_client_engagement(
    client_id: UUID,
    engagement_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    check_client_access(auth, client_id, db)
    engagement = (
        db.query(ClientEngagement)
        .filter(
            ClientEngagement.id == engagement_id,
            ClientEngagement.client_id == client_id,
        )
        .first()
    )
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    removed = remove_engagement(db, client_id, engagement.template_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Engagement not found")


# ---------------------------------------------------------------------------
# PATCH /clients/{client_id}/engagements/{engagement_id}
# ---------------------------------------------------------------------------

@router.patch(
    "/clients/{client_id}/engagements/{engagement_id}",
    response_model=ClientEngagementResponse,
    summary="Update engagement overrides",
)
async def update_client_engagement(
    client_id: UUID,
    engagement_id: UUID,
    body: UpdateEngagementRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientEngagementResponse:
    check_client_access(auth, client_id, db)
    engagement = (
        db.query(ClientEngagement)
        .options(joinedload(ClientEngagement.template).joinedload(EngagementTemplate.tasks))
        .filter(
            ClientEngagement.id == engagement_id,
            ClientEngagement.client_id == client_id,
        )
        .first()
    )
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(engagement, key, value)
    db.commit()
    db.refresh(engagement)
    return ClientEngagementResponse.model_validate(engagement)


# ---------------------------------------------------------------------------
# POST /clients/{client_id}/engagements/generate
# ---------------------------------------------------------------------------

@router.post(
    "/clients/{client_id}/engagements/generate",
    response_model=GenerateTasksResponse,
    summary="Manually trigger task generation for this client",
)
async def trigger_generation(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> GenerateTasksResponse:
    check_client_access(auth, client_id, db)
    results = generate_upcoming_tasks(db, days_ahead=90, client_id=client_id)
    return GenerateTasksResponse(
        tasks_created=len(results),
        details=results,
    )
