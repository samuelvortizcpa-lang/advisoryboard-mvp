"""
Notification preferences API router.

Endpoints:
  GET   /notifications/preferences   — get (or create) current user's prefs
  PATCH /notifications/preferences   — update preferences
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.notification_preference import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from app.services import notification_service
from app.services.auth_context import AuthContext, get_auth

router = APIRouter()


@router.get(
    "/notifications/preferences",
    response_model=NotificationPreferenceResponse,
    summary="Get notification preferences",
)
async def get_preferences(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> NotificationPreferenceResponse:
    prefs = notification_service.get_or_create_preferences(
        db, auth.user_id, str(auth.org_id)
    )
    return prefs


@router.patch(
    "/notifications/preferences",
    response_model=NotificationPreferenceResponse,
    summary="Update notification preferences",
)
async def update_preferences(
    body: NotificationPreferenceUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> NotificationPreferenceResponse:
    prefs = notification_service.get_or_create_preferences(
        db, auth.user_id, str(auth.org_id)
    )
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(prefs, key, value)
    db.commit()
    db.refresh(prefs)
    return prefs
