"""
User endpoints — onboarding status, etc.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user_subscription import UserSubscription
from app.schemas.users import OnboardingUpdateRequest, OnboardingUpdateResponse
from app.services.auth_context import AuthContext, get_auth

router = APIRouter(prefix="/users", tags=["users"])


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
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == auth.user_id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription record not found",
        )

    sub.has_completed_onboarding = body.completed
    db.commit()
    db.refresh(sub)

    return OnboardingUpdateResponse(
        has_completed_onboarding=sub.has_completed_onboarding,
    )
