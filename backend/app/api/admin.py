"""
Admin endpoints for subscription management.

Routes (all require Clerk JWT auth):
  GET   /api/admin/subscriptions
  GET   /api/admin/subscriptions/summary
  PUT   /api/admin/subscriptions/{user_id}
  POST  /api/admin/subscriptions/{user_id}/reset-usage
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.services.subscription_service import TIER_DEFAULTS

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────────────


class SubscriptionResponse(BaseModel):
    id: UUID
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    tier: str
    strategic_queries_limit: int
    strategic_queries_used: int
    billing_period_start: datetime
    billing_period_end: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    usage_percentage: float

    class Config:
        from_attributes = True


class TierUpdateRequest(BaseModel):
    tier: str

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        if v not in TIER_DEFAULTS:
            raise ValueError(f"Invalid tier. Must be one of: {', '.join(TIER_DEFAULTS)}")
        return v


class SubscriptionsSummary(BaseModel):
    total_users: int
    by_tier: dict[str, int]
    users_near_limit: int
    users_over_limit: int


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _build_response(sub: UserSubscription, user: Optional[User] = None) -> SubscriptionResponse:
    limit = sub.strategic_queries_limit
    used = sub.strategic_queries_used
    pct = (used / limit * 100) if limit > 0 else 0.0

    user_name = None
    user_email = None
    if user:
        parts = [user.first_name, user.last_name]
        user_name = " ".join(p for p in parts if p) or None
        user_email = user.email

    return SubscriptionResponse(
        id=sub.id,
        user_id=sub.user_id,
        user_email=user_email,
        user_name=user_name,
        tier=sub.tier,
        strategic_queries_limit=limit,
        strategic_queries_used=used,
        billing_period_start=sub.billing_period_start,
        billing_period_end=sub.billing_period_end,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        usage_percentage=round(pct, 1),
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get(
    "/subscriptions",
    response_model=List[SubscriptionResponse],
    summary="List all user subscriptions",
)
async def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[SubscriptionResponse]:
    rows = (
        db.query(UserSubscription, User)
        .outerjoin(User, UserSubscription.user_id == User.clerk_id)
        .order_by(UserSubscription.created_at.desc())
        .all()
    )
    return [_build_response(sub, user) for sub, user in rows]


@router.get(
    "/subscriptions/summary",
    response_model=SubscriptionsSummary,
    summary="Subscription overview stats",
)
async def subscriptions_summary(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> SubscriptionsSummary:
    subs = db.query(UserSubscription).all()

    by_tier: dict[str, int] = {t: 0 for t in TIER_DEFAULTS}
    near = 0
    over = 0

    for s in subs:
        by_tier[s.tier] = by_tier.get(s.tier, 0) + 1
        if s.strategic_queries_limit > 0:
            pct = s.strategic_queries_used / s.strategic_queries_limit * 100
            if pct >= 100:
                over += 1
            elif pct > 80:
                near += 1

    return SubscriptionsSummary(
        total_users=len(subs),
        by_tier=by_tier,
        users_near_limit=near,
        users_over_limit=over,
    )


@router.put(
    "/subscriptions/{user_id}",
    response_model=SubscriptionResponse,
    summary="Update a user's subscription tier",
)
async def update_subscription(
    user_id: str,
    body: TierUpdateRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> SubscriptionResponse:
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    tier_config = TIER_DEFAULTS[body.tier]
    sub.tier = body.tier
    sub.strategic_queries_limit = tier_config["strategic_queries_limit"]
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sub)

    user = db.query(User).filter(User.clerk_id == user_id).first()
    return _build_response(sub, user)


@router.post(
    "/subscriptions/{user_id}/reset-usage",
    response_model=SubscriptionResponse,
    summary="Reset a user's usage count and billing period",
)
async def reset_usage(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> SubscriptionResponse:
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    now = datetime.now(timezone.utc)
    sub.strategic_queries_used = 0
    sub.billing_period_start = now
    sub.billing_period_end = now + timedelta(days=30)
    sub.updated_at = now
    db.commit()
    db.refresh(sub)

    user = db.query(User).filter(User.clerk_id == user_id).first()
    return _build_response(sub, user)
