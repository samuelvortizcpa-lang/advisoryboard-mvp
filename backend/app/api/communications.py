"""Client communication endpoints — send emails, manage templates."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client_communication import ClientCommunication
from app.models.follow_up_reminder import FollowUpReminder
from app.models.user import User
from app.schemas.communication import (
    CommunicationResponse,
    CommunicationSendRequest,
    CommunicationSendResponse,
    DraftEmailRequest,
    DraftEmailResponse,
    DraftQuarterlyEstimateRequest,
    DraftQuarterlyEstimateResponse,
    FollowUpReminderResponse,
    RenderTemplateRequest,
    RenderedTemplate,
    SchedulingUrlResponse,
    SchedulingUrlUpdate,
    TemplateCreateRequest,
    TemplateResponse,
    TemplateUpdateRequest,
)
from app.services import communication_service
from app.services.auth_context import AuthContext, check_client_access, get_auth

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Send email
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/communications/send",
    response_model=CommunicationSendResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_communication(
    client_id: UUID,
    body: CommunicationSendRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> CommunicationSendResponse:
    """Send an email to a client and log it."""
    check_client_access(auth, client_id, db)

    comm = communication_service.send_client_email(
        user_id=auth.user_id,
        client_id=client_id,
        subject=body.subject,
        body_html=body.body_html,
        recipient_email=body.recipient_email,
        recipient_name=body.recipient_name,
        template_id=body.template_id,
        metadata=body.metadata,
        db=db,
        thread_id=body.thread_id,
        thread_type=body.thread_type,
        thread_year=body.thread_year,
        thread_quarter=body.thread_quarter,
    )

    # Increment template usage if a template was used
    if body.template_id:
        communication_service.increment_template_usage(body.template_id, db)

    # Create follow-up reminder if requested
    follow_up = None
    if body.follow_up_days:
        reminder = FollowUpReminder(
            communication_id=comm.id,
            client_id=client_id,
            user_id=auth.user_id,
            remind_at=datetime.now(timezone.utc) + timedelta(days=body.follow_up_days),
            status="pending",
        )
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        follow_up = FollowUpReminderResponse.model_validate(reminder)

    return CommunicationSendResponse(
        communication=CommunicationResponse.model_validate(comm),
        follow_up=follow_up,
    )


# ---------------------------------------------------------------------------
# Communication history
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/communications",
    response_model=List[CommunicationResponse],
)
async def list_communications(
    client_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[CommunicationResponse]:
    """Return communication history for a client."""
    check_client_access(auth, client_id, db)

    comms = communication_service.get_communication_history(
        client_id=client_id,
        user_id=auth.user_id,
        db=db,
        limit=limit,
    )
    return [CommunicationResponse.model_validate(c) for c in comms]


# ---------------------------------------------------------------------------
# Thread history
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/communications/thread/{thread_id}",
    response_model=List[CommunicationResponse],
)
async def get_thread_history(
    client_id: UUID,
    thread_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[CommunicationResponse]:
    """Return all communications in a thread, ordered chronologically."""
    check_client_access(auth, client_id, db)

    comms = communication_service.get_thread_history(db, client_id, thread_id)
    return [CommunicationResponse.model_validate(c) for c in comms]


# ---------------------------------------------------------------------------
# Render template preview
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/communications/render-template",
    response_model=RenderedTemplate,
)
async def render_template(
    client_id: UUID,
    body: RenderTemplateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> RenderedTemplate:
    """Preview a rendered template with merge variables filled in."""
    check_client_access(auth, client_id, db)

    try:
        rendered = communication_service.render_template(
            template_id=body.template_id,
            user_id=auth.user_id,
            client_id=client_id,
            db=db,
            extra_vars=body.extra_vars,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return RenderedTemplate(**rendered)


# ---------------------------------------------------------------------------
# Templates CRUD
# ---------------------------------------------------------------------------


@router.get("/communications/templates", response_model=List[TemplateResponse])
async def list_templates(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[TemplateResponse]:
    """Return all templates available to the current user."""
    templates = communication_service.get_templates(auth.user_id, db)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.post(
    "/communications/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    body: TemplateCreateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> TemplateResponse:
    """Create a custom email template."""
    try:
        template = communication_service.create_template(
            user_id=auth.user_id,
            name=body.name,
            subject_template=body.subject_template,
            body_template=body.body_template,
            template_type=body.template_type,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return TemplateResponse.model_validate(template)


@router.patch(
    "/communications/templates/{template_id}",
    response_model=TemplateResponse,
)
async def update_template(
    template_id: UUID,
    body: TemplateUpdateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> TemplateResponse:
    """Update a custom email template."""
    updates = body.model_dump(exclude_unset=True)
    try:
        template = communication_service.update_template(
            template_id=template_id,
            user_id=auth.user_id,
            updates=updates,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return TemplateResponse.model_validate(template)


@router.delete(
    "/communications/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    """Soft-delete a custom email template."""
    try:
        communication_service.delete_template(
            template_id=template_id,
            user_id=auth.user_id,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ---------------------------------------------------------------------------
# AI Draft
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/communications/draft",
    response_model=DraftEmailResponse,
)
async def draft_email(
    client_id: UUID,
    body: DraftEmailRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DraftEmailResponse:
    """Generate an AI-drafted email for a client using contextual awareness."""
    check_client_access(auth, client_id, db)

    try:
        draft = await communication_service.draft_email_with_ai(
            user_id=auth.user_id,
            client_id=client_id,
            purpose=body.purpose,
            additional_context=body.additional_context,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("AI draft failed for client %s", client_id)
        raise HTTPException(
            status_code=502,
            detail="Failed to generate AI draft. Please try again.",
        )

    return DraftEmailResponse(**draft)


# ---------------------------------------------------------------------------
# Quarterly Estimate Draft
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/communications/draft-quarterly-estimate",
    response_model=DraftQuarterlyEstimateResponse,
)
async def draft_quarterly_estimate(
    client_id: UUID,
    body: DraftQuarterlyEstimateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DraftQuarterlyEstimateResponse:
    """Draft a quarterly estimated tax payment email with thread and open item awareness."""
    check_client_access(auth, client_id, db)

    try:
        from app.services.quarterly_estimate_service import draft_quarterly_estimate_email

        result = await draft_quarterly_estimate_email(
            db=db,
            client_id=client_id,
            user_id=auth.user_id,
            tax_year=body.tax_year,
            quarter=body.quarter,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception(
            "Quarterly estimate draft failed for client %s Q%d %d",
            client_id, body.quarter, body.tax_year,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to generate quarterly estimate draft. Please try again.",
        )

    return DraftQuarterlyEstimateResponse(**result)


# ---------------------------------------------------------------------------
# Follow-up reminders
# ---------------------------------------------------------------------------


@router.post(
    "/follow-up-reminders/{reminder_id}/resolve",
    response_model=FollowUpReminderResponse,
)
async def resolve_follow_up(
    reminder_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> FollowUpReminderResponse:
    """Mark a follow-up reminder as resolved (client responded)."""
    reminder = (
        db.query(FollowUpReminder)
        .filter(
            FollowUpReminder.id == reminder_id,
            FollowUpReminder.user_id == auth.user_id,
        )
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.status = "resolved"
    reminder.triggered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(reminder)
    return FollowUpReminderResponse.model_validate(reminder)


@router.post(
    "/follow-up-reminders/{reminder_id}/dismiss",
    response_model=FollowUpReminderResponse,
)
async def dismiss_follow_up(
    reminder_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> FollowUpReminderResponse:
    """Dismiss a follow-up reminder."""
    reminder = (
        db.query(FollowUpReminder)
        .filter(
            FollowUpReminder.id == reminder_id,
            FollowUpReminder.user_id == auth.user_id,
        )
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")

    reminder.status = "dismissed"
    reminder.triggered_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(reminder)
    return FollowUpReminderResponse.model_validate(reminder)


# ---------------------------------------------------------------------------
# Last communication
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/communications/last",
    response_model=Optional[CommunicationResponse],
)
async def get_last_communication(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> Optional[CommunicationResponse]:
    """Return the most recent communication sent to this client."""
    check_client_access(auth, client_id, db)

    comm = (
        db.query(ClientCommunication)
        .filter(
            ClientCommunication.client_id == client_id,
            ClientCommunication.user_id == auth.user_id,
        )
        .order_by(ClientCommunication.sent_at.desc())
        .first()
    )
    if not comm:
        return None
    return CommunicationResponse.model_validate(comm)


# ---------------------------------------------------------------------------
# Scheduling URL
# ---------------------------------------------------------------------------


@router.patch("/users/me/scheduling-url", response_model=SchedulingUrlResponse)
async def update_scheduling_url(
    body: SchedulingUrlUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> SchedulingUrlResponse:
    """Update the current user's scheduling link (Calendly, Cal.com, etc.)."""
    db_user = db.query(User).filter(User.clerk_id == auth.user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.scheduling_url = body.scheduling_url
    db.commit()
    db.refresh(db_user)
    return SchedulingUrlResponse(scheduling_url=db_user.scheduling_url)
