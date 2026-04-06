"""
User endpoints — onboarding status, tooltip dismissals, etc.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user_subscription import UserSubscription
from app.schemas.users import (
    OnboardingUpdateRequest,
    OnboardingUpdateResponse,
    TooltipDismissRequest,
    TooltipDismissResponse,
)
from app.services.auth_context import AuthContext, get_auth

router = APIRouter(prefix="/users", tags=["users"])


def _get_subscription(db: Session, user_id: str) -> UserSubscription:
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user_id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription record not found",
        )
    return sub


@router.patch(
    "/onboarding",
    response_model=OnboardingUpdateResponse,
    summary="Update onboarding completion status",
)
async def update_onboarding(
    body: OnboardingUpdateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> OnboardingUpdateResponse:
    sub = _get_subscription(db, auth.user_id)
    sub.has_completed_onboarding = body.completed
    db.commit()
    db.refresh(sub)
    return OnboardingUpdateResponse(
        has_completed_onboarding=sub.has_completed_onboarding,
    )


@router.patch(
    "/tooltips",
    response_model=TooltipDismissResponse,
    summary="Dismiss a contextual tooltip",
)
async def dismiss_tooltip(
    body: TooltipDismissRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> TooltipDismissResponse:
    sub = _get_subscription(db, auth.user_id)
    current: list = sub.dismissed_tooltips or []
    if body.tooltip_id not in current:
        sub.dismissed_tooltips = [*current, body.tooltip_id]
        db.commit()
        db.refresh(sub)
    return TooltipDismissResponse(
        dismissed_tooltips=sub.dismissed_tooltips or [],
    )
