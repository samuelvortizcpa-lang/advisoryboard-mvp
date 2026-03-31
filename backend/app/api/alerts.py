"""
Smart Alerts API endpoints.

Routes (all require Clerk JWT auth):
  GET  /api/alerts          — list computed alerts for current user
  POST /api/alerts/dismiss  — dismiss a specific alert
  GET  /api/alerts/summary  — counts by severity
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.dismissed_alert import DismissedAlert
from app.models.follow_up_reminder import FollowUpReminder
from app.services.alerts_service import compute_alerts, compute_summary, invalidate_alerts_cache
from app.services.auth_context import AuthContext, get_auth

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AlertItem(BaseModel):
    id: str
    type: str
    severity: str
    client_id: str
    client_name: str
    message: str
    related_id: str
    created_at: str


class AlertsListResponse(BaseModel):
    alerts: List[AlertItem]
    total: int


class AlertsSummaryResponse(BaseModel):
    critical: int
    warning: int
    info: int
    total: int


class DismissRequest(BaseModel):
    alert_type: str = Field(..., max_length=100)
    related_id: str = Field(..., max_length=100)


class DismissResponse(BaseModel):
    dismissed: bool


# ---------------------------------------------------------------------------
# GET /api/alerts
# ---------------------------------------------------------------------------


@router.get(
    "/alerts",
    response_model=AlertsListResponse,
    summary="List all active alerts for the current user",
)
async def list_alerts(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> AlertsListResponse:
    alerts = compute_alerts(db, org_id=auth.org_id, clerk_user_id=auth.user_id)

    return AlertsListResponse(
        alerts=[AlertItem(**a) for a in alerts],
        total=len(alerts),
    )


# ---------------------------------------------------------------------------
# POST /api/alerts/dismiss
# ---------------------------------------------------------------------------


@router.post(
    "/alerts/dismiss",
    response_model=DismissResponse,
    summary="Dismiss a specific alert",
)
async def dismiss_alert(
    request: DismissRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DismissResponse:

    # Parse related_id to UUID
    try:
        related_uuid = UUID(request.related_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid related_id format",
        )

    # Check if already dismissed (upsert-like)
    existing = (
        db.query(DismissedAlert)
        .filter(
            DismissedAlert.user_id == auth.user_id,
            DismissedAlert.alert_type == request.alert_type,
            DismissedAlert.related_id == related_uuid,
        )
        .first()
    )

    if not existing:
        dismissed = DismissedAlert(
            user_id=auth.user_id,
            alert_type=request.alert_type,
            related_id=related_uuid,
        )
        db.add(dismissed)

        # When dismissing a follow_up_due alert, also mark the reminder as dismissed
        if request.alert_type == "follow_up_due":
            reminder = (
                db.query(FollowUpReminder)
                .filter(
                    FollowUpReminder.communication_id == related_uuid,
                    FollowUpReminder.user_id == auth.user_id,
                )
                .first()
            )
            if reminder:
                reminder.status = "dismissed"

        db.commit()
        invalidate_alerts_cache(auth.org_id, auth.user_id)

    return DismissResponse(dismissed=True)


# ---------------------------------------------------------------------------
# GET /api/alerts/summary
# ---------------------------------------------------------------------------


@router.get(
    "/alerts/summary",
    response_model=AlertsSummaryResponse,
    summary="Get alert counts by severity",
)
async def alerts_summary(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> AlertsSummaryResponse:
    summary = compute_summary(db, org_id=auth.org_id, clerk_user_id=auth.user_id)

    return AlertsSummaryResponse(**summary)
