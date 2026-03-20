"""
Admin endpoints for subscription management and platform overview.

Auth: Clerk JWT (production) OR X-Admin-Key header (local admin dashboard).

Routes:
  GET   /api/admin/users
  GET   /api/admin/overview
  GET   /api/admin/subscriptions
  GET   /api/admin/subscriptions/summary
  PUT   /api/admin/subscriptions/{user_id}
  POST  /api/admin/subscriptions/{user_id}/reset-usage
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

logger = logging.getLogger(__name__)
from app.models.client import Client
from app.models.document import Document
from app.models.token_usage import TokenUsage
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.services.subscription_service import TIER_DEFAULTS

router = APIRouter()


# ─── Admin auth guard ────────────────────────────────────────────────────────


async def verify_admin_access(request: Request) -> None:
    """
    Allow access if EITHER:
      a) X-Admin-Key header matches ADMIN_API_KEY, OR
      b) Standard Clerk JWT belongs to ADMIN_USER_ID.
    Raises 403 if neither method passes.
    """
    settings = get_settings()

    # Method 1: static API key via X-Admin-Key header
    api_key = request.headers.get("X-Admin-Key")
    if api_key and settings.admin_api_key and api_key == settings.admin_api_key:
        return

    # Method 2: Clerk JWT (existing flow)
    from fastapi.security import HTTPBearer
    bearer = HTTPBearer(auto_error=False)
    credentials = await bearer(request)
    if credentials:
        try:
            from app.core.auth import verify_clerk_token
            payload = await verify_clerk_token(credentials.credentials)
            user_id = payload.get("sub")
            if settings.admin_user_id and user_id == settings.admin_user_id:
                return
        except HTTPException:
            pass  # JWT invalid/expired — fall through to 403

    raise HTTPException(status_code=403, detail="Admin access required")


# ─── Admin user / overview schemas ───────────────────────────────────────────


class AdminUserResponse(BaseModel):
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    tier: str
    stripe_status: Optional[str] = None
    payment_status: Optional[str] = None
    created_at: datetime
    client_count: int = 0
    document_count: int = 0
    total_queries: int = 0
    total_cost: float = 0.0
    last_active_at: Optional[datetime] = None
    days_since_active: Optional[int] = None
    queries_last_7_days: int = 0
    storage_used_mb: float = 0.0

    class Config:
        from_attributes = True


class AdminOverviewResponse(BaseModel):
    total_users: int
    total_users_by_tier: dict[str, int]
    active_last_7_days: int
    active_last_30_days: int
    total_revenue_mtd: float
    total_documents: int
    total_queries_today: int
    mrr: float


# ─── Admin user / overview endpoints ─────────────────────────────────────────


@router.get(
    "/users",
    response_model=List[AdminUserResponse],
    summary="List all users with comprehensive activity metrics",
)
async def list_admin_users(
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> List[AdminUserResponse]:
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Base: all subscriptions with user info
    subs = (
        db.query(UserSubscription, User)
        .outerjoin(User, UserSubscription.user_id == User.clerk_id)
        .order_by(UserSubscription.created_at.desc())
        .all()
    )

    results: list[AdminUserResponse] = []
    for sub, user in subs:
        clerk_id = sub.user_id

        # User name / email
        user_name = None
        user_email = None
        if user:
            parts = [user.first_name, user.last_name]
            user_name = " ".join(p for p in parts if p) or None
            user_email = user.email

        # Client count (clients.owner_id is UUID FK to users.id)
        client_count = 0
        if user:
            client_count = (
                db.query(func.count(Client.id))
                .filter(Client.owner_id == user.id)
                .scalar()
            ) or 0

        # Document count + storage (documents.uploaded_by is UUID FK to users.id)
        doc_count = 0
        storage_bytes = 0
        if user:
            doc_agg = (
                db.query(
                    func.count(Document.id),
                    func.coalesce(func.sum(Document.file_size), 0),
                )
                .filter(Document.uploaded_by == user.id)
                .first()
            )
            if doc_agg:
                doc_count = doc_agg[0] or 0
                storage_bytes = doc_agg[1] or 0

        # Token usage aggregates (token_usage.user_id is clerk_id string)
        usage_agg = (
            db.query(
                func.count(TokenUsage.id),
                func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0),
                func.max(TokenUsage.created_at),
            )
            .filter(TokenUsage.user_id == clerk_id)
            .first()
        )
        total_queries = (usage_agg[0] or 0) if usage_agg else 0
        total_cost = float(usage_agg[1] or 0) if usage_agg else 0.0
        last_active_at = usage_agg[2] if usage_agg else None

        # Queries last 7 days
        q7 = (
            db.query(func.count(TokenUsage.id))
            .filter(
                TokenUsage.user_id == clerk_id,
                TokenUsage.created_at >= seven_days_ago,
            )
            .scalar()
        ) or 0

        # Days since active
        days_since = None
        if last_active_at:
            if last_active_at.tzinfo is None:
                last_active_at = last_active_at.replace(tzinfo=timezone.utc)
            days_since = (now - last_active_at).days

        results.append(
            AdminUserResponse(
                user_id=clerk_id,
                user_email=user_email,
                user_name=user_name,
                tier=sub.tier,
                stripe_status=sub.stripe_status,
                payment_status=sub.payment_status,
                created_at=sub.created_at,
                client_count=client_count,
                document_count=doc_count,
                total_queries=total_queries,
                total_cost=round(total_cost, 4),
                last_active_at=last_active_at,
                days_since_active=days_since,
                queries_last_7_days=q7,
                storage_used_mb=round(storage_bytes / 1048576, 2),
            )
        )

    return results


@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="Platform-wide overview metrics",
)
async def admin_overview(
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> AdminOverviewResponse:
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Total users by tier
    tier_rows = (
        db.query(UserSubscription.tier, func.count(UserSubscription.id))
        .group_by(UserSubscription.tier)
        .all()
    )
    by_tier: dict[str, int] = {}
    total_users = 0
    for tier, cnt in tier_rows:
        by_tier[tier] = cnt
        total_users += cnt

    # Active users (distinct user_ids with queries in time windows)
    active_7 = (
        db.query(func.count(func.distinct(TokenUsage.user_id)))
        .filter(TokenUsage.created_at >= seven_days_ago)
        .scalar()
    ) or 0

    active_30 = (
        db.query(func.count(func.distinct(TokenUsage.user_id)))
        .filter(TokenUsage.created_at >= thirty_days_ago)
        .scalar()
    ) or 0

    # Revenue MTD (AI cost, not subscription revenue)
    revenue_mtd = (
        db.query(func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0))
        .filter(TokenUsage.created_at >= month_start)
        .scalar()
    ) or 0

    # Total documents
    total_docs = db.query(func.count(Document.id)).scalar() or 0

    # Queries today
    queries_today = (
        db.query(func.count(TokenUsage.id))
        .filter(TokenUsage.created_at >= today_start)
        .scalar()
    ) or 0

    # MRR: simple calculation
    mrr = (
        by_tier.get("starter", 0) * 99
        + by_tier.get("professional", 0) * 149
        + by_tier.get("firm", 0) * 249
    )

    return AdminOverviewResponse(
        total_users=total_users,
        total_users_by_tier=by_tier,
        active_last_7_days=active_7,
        active_last_30_days=active_30,
        total_revenue_mtd=round(float(revenue_mtd), 4),
        total_documents=total_docs,
        total_queries_today=queries_today,
        mrr=float(mrr),
    )


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
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
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
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
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
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
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
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
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
