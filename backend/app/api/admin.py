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
  POST  /api/admin/evaluate-rag/{client_id}
  GET   /api/admin/evaluations
  GET   /api/admin/evaluations/compare
  POST  /api/admin/reprocess-documents
  GET   /api/admin/reprocess-status/{task_id}
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import cast, func, Date
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

logger = logging.getLogger(__name__)
from app.models.client import Client
from app.models.document import Document
from app.models.token_usage import TokenUsage
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.services.auth_context import AuthContext, get_auth, require_admin
from app.services.subscription_service import TIER_DEFAULTS

# Tier → monthly price (matches overview endpoint MRR calc)
_TIER_MRR: dict[str, int] = {
    "free": 0,
    "starter": 99,
    "professional": 149,
    "firm": 349,
}

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

    # Method 1: static API key via X-Admin-Key header (constant-time comparison)
    api_key = request.headers.get("X-Admin-Key")
    if api_key and settings.admin_api_key and hmac.compare_digest(
        api_key.encode("utf-8"), settings.admin_api_key.encode("utf-8")
    ):
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
            if settings.admin_user_id and user_id and hmac.compare_digest(
                user_id.encode("utf-8"), settings.admin_user_id.encode("utf-8")
            ):
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
        + by_tier.get("firm", 0) * 349
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
    sonnet_queries_limit: int = 0
    sonnet_queries_used: int = 0
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
        sonnet_queries_limit=sub.sonnet_queries_limit,
        sonnet_queries_used=sub.sonnet_queries_used,
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
    sub.sonnet_queries_limit = tier_config["sonnet_queries_limit"]
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


# ─── MRR History ────────────────────────────────────────────────────────────


@router.get(
    "/mrr-history",
    summary="Daily MRR snapshots for charting",
)
async def mrr_history(
    days: int = Query(default=30, ge=1, le=90),
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> list[dict]:
    """
    Reconstruct daily MRR from user_subscriptions.

    For each day in the range, determine which subscriptions existed (created_at <= day)
    and approximate tier changes via updated_at. Returns the right response shape;
    true daily snapshots can be added later.
    """
    today = date.today()
    start = today - timedelta(days=days - 1)

    # Load all subscriptions once
    subs = db.query(UserSubscription).all()

    result: list[dict] = []
    for offset in range(days):
        day = start + timedelta(days=offset)

        mrr = 0.0
        user_count = 0
        paid_count = 0

        for sub in subs:
            # Skip subscriptions created after this day
            created = sub.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created.date() > day:
                continue

            user_count += 1

            # If updated_at > day AND updated_at != created_at, the tier may have
            # changed. We can't know the old tier, so for days before the last
            # update we assume free. For days >= updated_at we use current tier.
            updated = sub.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)

            if updated.date() > day and updated.date() != created.date():
                tier_price = 0
            else:
                tier_price = _TIER_MRR.get(sub.tier, 0)

            mrr += tier_price
            if tier_price > 0:
                paid_count += 1

        result.append({
            "date": day.isoformat(),
            "mrr": mrr,
            "user_count": user_count,
            "paid_count": paid_count,
        })

    return result


# ─── User Detail ────────────────────────────────────────────────────────────


@router.get(
    "/users/{user_id}/detail",
    summary="Detailed activity for a single user",
)
async def user_detail(
    user_id: str,
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    user = db.query(User).filter(User.clerk_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == user_id)
        .first()
    )

    # --- User info ---
    user_name = " ".join(p for p in [user.first_name, user.last_name] if p) or None

    last_query = (
        db.query(func.max(TokenUsage.created_at))
        .filter(TokenUsage.user_id == user_id)
        .scalar()
    )
    last_upload = (
        db.query(func.max(Document.upload_date))
        .filter(Document.uploaded_by == user.id)
        .scalar()
    )
    timestamps = [t for t in [last_query, last_upload] if t is not None]
    last_active = max(timestamps) if timestamps else None

    user_info = {
        "user_id": user_id,
        "email": user.email,
        "name": user_name,
        "tier": sub.tier if sub else "free",
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_active": last_active.isoformat() if last_active else None,
    }

    # --- Subscription ---
    subscription = None
    if sub:
        subscription = {
            "tier": sub.tier,
            "strategic_queries_used": sub.strategic_queries_used,
            "strategic_queries_limit": sub.strategic_queries_limit,
            "billing_period_start": sub.billing_period_start.isoformat() if sub.billing_period_start else None,
            "billing_period_end": sub.billing_period_end.isoformat() if sub.billing_period_end else None,
        }

    # --- Clients ---
    clients_raw = db.query(Client).filter(Client.owner_id == user.id).all()
    clients_out: list[dict] = []
    for c in clients_raw:
        doc_count = (
            db.query(func.count(Document.id))
            .filter(Document.client_id == c.id)
            .scalar()
        ) or 0
        last_doc = (
            db.query(func.max(Document.upload_date))
            .filter(Document.client_id == c.id)
            .scalar()
        )
        query_count = (
            db.query(func.count(TokenUsage.id))
            .filter(TokenUsage.client_id == c.id)
            .scalar()
        ) or 0
        clients_out.append({
            "id": str(c.id),
            "name": c.name,
            "document_count": doc_count,
            "last_document_upload": last_doc.isoformat() if last_doc else None,
            "query_count": query_count,
        })

    # --- Activity timeline (last 50 token_usage entries) ---
    recent_usage = (
        db.query(TokenUsage)
        .filter(TokenUsage.user_id == user_id)
        .order_by(TokenUsage.created_at.desc())
        .limit(50)
        .all()
    )
    client_ids = {u.client_id for u in recent_usage if u.client_id}
    client_map: dict = {}
    if client_ids:
        for cid, cname in db.query(Client.id, Client.name).filter(Client.id.in_(client_ids)).all():
            client_map[cid] = cname

    activity_timeline = [
        {
            "timestamp": u.created_at.isoformat(),
            "endpoint": u.endpoint,
            "query_type": u.query_type,
            "model": u.model,
            "prompt_tokens": u.prompt_tokens,
            "completion_tokens": u.completion_tokens,
            "cost": float(u.estimated_cost_usd),
            "client_name": client_map.get(u.client_id),
        }
        for u in recent_usage
    ]

    # --- Daily activity (last 30 days) ---
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    daily_query_rows = (
        db.query(
            cast(TokenUsage.created_at, Date).label("day"),
            func.count(TokenUsage.id),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0),
        )
        .filter(
            TokenUsage.user_id == user_id,
            TokenUsage.created_at >= thirty_days_ago,
        )
        .group_by("day")
        .all()
    )
    daily_doc_rows = (
        db.query(
            cast(Document.upload_date, Date).label("day"),
            func.count(Document.id),
        )
        .filter(
            Document.uploaded_by == user.id,
            Document.upload_date >= thirty_days_ago,
        )
        .group_by("day")
        .all()
    )
    docs_by_day = {row[0]: row[1] for row in daily_doc_rows}
    daily_activity = [
        {
            "date": row[0].isoformat(),
            "queries": row[1],
            "documents_uploaded": docs_by_day.get(row[0], 0),
            "cost": round(float(row[2]), 4),
        }
        for row in daily_query_rows
    ]

    # --- Documents summary ---
    total_docs = (
        db.query(func.count(Document.id))
        .filter(Document.uploaded_by == user.id)
        .scalar()
    ) or 0
    processed_docs = (
        db.query(func.count(Document.id))
        .filter(Document.uploaded_by == user.id, Document.processed == True)  # noqa: E712
        .scalar()
    ) or 0
    recent_docs = (
        db.query(Document)
        .filter(Document.uploaded_by == user.id)
        .order_by(Document.upload_date.desc())
        .limit(5)
        .all()
    )
    documents = {
        "total": total_docs,
        "processed": processed_docs,
        "unprocessed": total_docs - processed_docs,
        "recent": [
            {
                "filename": d.filename,
                "upload_date": d.upload_date.isoformat() if d.upload_date else None,
                "file_type": d.file_type,
                "processed": d.processed,
            }
            for d in recent_docs
        ],
    }

    return {
        "user": user_info,
        "subscription": subscription,
        "clients": clients_out,
        "activity_timeline": activity_timeline,
        "daily_activity": daily_activity,
        "documents": documents,
    }


# ─── Conversion Funnel ──────────────────────────────────────────────────────


@router.get(
    "/conversion-funnel",
    summary="Tier distribution and conversion metrics",
)
async def conversion_funnel(
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    subs = db.query(UserSubscription).all()

    by_tier: dict[str, int] = {"free": 0, "starter": 0, "professional": 0, "firm": 0}
    upgrade_deltas: list[float] = []

    for s in subs:
        by_tier[s.tier] = by_tier.get(s.tier, 0) + 1

        # Estimate upgrade timing: if tier != free and updated_at differs from
        # created_at by more than a minute, they likely upgraded
        if s.tier != "free" and s.created_at and s.updated_at:
            created = s.created_at
            updated = s.updated_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            delta = (updated - created).total_seconds()
            if delta > 60:
                upgrade_deltas.append(delta / 86400)

    total_users = len(subs)
    paid_users = total_users - by_tier.get("free", 0)
    conversion_rate = round((paid_users / total_users * 100) if total_users > 0 else 0, 1)
    avg_days_to_upgrade = round(sum(upgrade_deltas) / len(upgrade_deltas), 1) if upgrade_deltas else None

    # Users who recently hit limits
    recently_hit_limits: list[dict] = []
    for s in subs:
        tier_config = TIER_DEFAULTS.get(s.tier, TIER_DEFAULTS["free"])
        limits_hit: list[str] = []

        # Query limit hit
        if s.strategic_queries_limit > 0 and s.strategic_queries_used >= s.strategic_queries_limit:
            limits_hit.append("strategic_queries")

        # Client limit hit
        max_clients = tier_config.get("max_clients")
        if max_clients is not None:
            user_obj = db.query(User).filter(User.clerk_id == s.user_id).first()
            if user_obj:
                client_count = (
                    db.query(func.count(Client.id))
                    .filter(Client.owner_id == user_obj.id)
                    .scalar()
                ) or 0
                if client_count >= max_clients:
                    limits_hit.append("clients")

        if limits_hit:
            user_obj = db.query(User).filter(User.clerk_id == s.user_id).first()
            user_name = None
            user_email = None
            if user_obj:
                user_name = " ".join(p for p in [user_obj.first_name, user_obj.last_name] if p) or None
                user_email = user_obj.email
            recently_hit_limits.append({
                "user_id": s.user_id,
                "email": user_email,
                "name": user_name,
                "tier": s.tier,
                "limits_hit": limits_hit,
            })

    return {
        "by_tier": by_tier,
        "total_users": total_users,
        "paid_users": paid_users,
        "conversion_rate": conversion_rate,
        "average_days_to_upgrade": avg_days_to_upgrade,
        "recently_hit_limits": recently_hit_limits,
    }


# ─── AI Costs ───────────────────────────────────────────────────────────────


@router.get(
    "/ai-costs",
    summary="AI cost analytics",
)
async def ai_costs(
    days: int = Query(default=30, ge=1, le=90),
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # --- Daily costs by model ---
    daily_rows = (
        db.query(
            cast(TokenUsage.created_at, Date).label("day"),
            TokenUsage.model,
            func.sum(TokenUsage.estimated_cost_usd),
            func.count(TokenUsage.id),
        )
        .filter(TokenUsage.created_at >= cutoff)
        .group_by("day", TokenUsage.model)
        .order_by("day")
        .all()
    )

    daily_map: dict[date, dict] = {}
    for day_val, model, cost, count in daily_rows:
        if day_val not in daily_map:
            daily_map[day_val] = {"date": day_val.isoformat(), "total_cost": 0.0, "by_model": {}}
        daily_map[day_val]["total_cost"] = round(daily_map[day_val]["total_cost"] + float(cost), 6)
        daily_map[day_val]["by_model"][model] = round(float(cost), 6)

    daily_costs = list(daily_map.values())

    # --- Per-user costs ---
    user_cost_rows = (
        db.query(
            TokenUsage.user_id,
            func.sum(TokenUsage.estimated_cost_usd),
            func.count(TokenUsage.id),
        )
        .filter(TokenUsage.created_at >= cutoff)
        .group_by(TokenUsage.user_id)
        .order_by(func.sum(TokenUsage.estimated_cost_usd).desc())
        .all()
    )

    user_ids = [r[0] for r in user_cost_rows]
    users_map = {u.clerk_id: u for u in db.query(User).filter(User.clerk_id.in_(user_ids)).all()} if user_ids else {}
    subs_map = {s.user_id: s for s in db.query(UserSubscription).filter(UserSubscription.user_id.in_(user_ids)).all()} if user_ids else {}

    per_user_costs = []
    for uid, total_cost_val, query_count in user_cost_rows:
        u = users_map.get(uid)
        s = subs_map.get(uid)
        total_c = float(total_cost_val)
        per_user_costs.append({
            "user_id": uid,
            "email": u.email if u else None,
            "name": (" ".join(p for p in [u.first_name, u.last_name] if p).strip() or None) if u else None,
            "tier": s.tier if s else "free",
            "total_cost": round(total_c, 4),
            "query_count": query_count,
            "avg_cost_per_query": round(total_c / query_count, 6) if query_count > 0 else 0,
        })

    # --- Totals ---
    total_cost = sum(float(r[1]) for r in user_cost_rows)
    days_elapsed = max(days, 1)
    projected_monthly = round((total_cost / days_elapsed) * 30, 2)

    # --- Top expensive queries ---
    top_queries = (
        db.query(TokenUsage)
        .filter(TokenUsage.created_at >= cutoff)
        .order_by(TokenUsage.estimated_cost_usd.desc())
        .limit(5)
        .all()
    )

    top_user_ids = {q.user_id for q in top_queries}
    top_client_ids = {q.client_id for q in top_queries if q.client_id}
    top_users = {u.clerk_id: u for u in db.query(User).filter(User.clerk_id.in_(top_user_ids)).all()} if top_user_ids else {}
    top_clients = {c.id: c.name for c in db.query(Client).filter(Client.id.in_(top_client_ids)).all()} if top_client_ids else {}

    top_expensive_queries = [
        {
            "timestamp": q.created_at.isoformat(),
            "user_email": top_users[q.user_id].email if q.user_id in top_users else None,
            "client_name": top_clients.get(q.client_id),
            "model": q.model,
            "endpoint": q.endpoint,
            "prompt_tokens": q.prompt_tokens,
            "completion_tokens": q.completion_tokens,
            "cost": round(float(q.estimated_cost_usd), 6),
        }
        for q in top_queries
    ]

    return {
        "daily_costs": daily_costs,
        "per_user_costs": per_user_costs,
        "total_cost": round(total_cost, 4),
        "projected_monthly": projected_monthly,
        "top_expensive_queries": top_expensive_queries,
    }


# ─── RAG Evaluation ─────────────────────────────────────────────────────────


@router.post(
    "/evaluate-rag/{client_id}",
    summary="Run RAG evaluation against a client's documents",
)
async def evaluate_rag(
    client_id: UUID,
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    """
    Run 8 test questions through the live RAG pipeline and score retrieval
    quality.  Takes 30-60s.  Each run costs ~$0.05-0.10 in LLM calls.
    """
    from app.services.rag_evaluator import run_evaluation
    from app.models.rag_evaluation import RagEvaluation

    # Use a synthetic user_id for eval runs
    eval_user_id = "eval_system"

    results = await run_evaluation(
        client_id=str(client_id),
        user_id=eval_user_id,
        db=db,
    )

    # Persist
    evaluation = RagEvaluation(
        client_id=client_id,
        user_id=eval_user_id,
        results=results,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    return {
        "evaluation_id": str(evaluation.id),
        "client_id": str(client_id),
        "created_at": evaluation.created_at.isoformat(),
        **results,
    }


@router.get(
    "/evaluations",
    summary="List past RAG evaluation results",
)
async def list_evaluations(
    client_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.models.rag_evaluation import RagEvaluation

    query = db.query(RagEvaluation).order_by(RagEvaluation.created_at.desc())
    if client_id:
        query = query.filter(RagEvaluation.client_id == client_id)
    evals = query.limit(limit).all()

    return [
        {
            "evaluation_id": str(e.id),
            "client_id": str(e.client_id),
            "created_at": e.created_at.isoformat(),
            "retrieval_hit_rate": e.results.get("retrieval_hit_rate"),
            "response_keyword_rate": e.results.get("response_keyword_rate"),
            "avg_latency_ms": e.results.get("avg_latency_ms"),
            "total_questions": e.results.get("total_questions"),
            "errors": e.results.get("errors", 0),
        }
        for e in evals
    ]


@router.get(
    "/evaluations/compare",
    summary="Compare two evaluation runs",
)
async def compare_evaluations_endpoint(
    eval_a_id: UUID = Query(..., description="Baseline evaluation ID"),
    eval_b_id: UUID = Query(..., description="New evaluation ID"),
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    from app.models.rag_evaluation import RagEvaluation
    from app.services.rag_evaluator import compare_evaluations

    eval_a = db.query(RagEvaluation).filter(RagEvaluation.id == eval_a_id).first()
    eval_b = db.query(RagEvaluation).filter(RagEvaluation.id == eval_b_id).first()

    if not eval_a or not eval_b:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    comparison = compare_evaluations(eval_a.results, eval_b.results)

    return {
        "baseline": {
            "id": str(eval_a.id),
            "created_at": eval_a.created_at.isoformat(),
            "retrieval_hit_rate": eval_a.results.get("retrieval_hit_rate"),
            "response_keyword_rate": eval_a.results.get("response_keyword_rate"),
        },
        "current": {
            "id": str(eval_b.id),
            "created_at": eval_b.created_at.isoformat(),
            "retrieval_hit_rate": eval_b.results.get("retrieval_hit_rate"),
            "response_keyword_rate": eval_b.results.get("response_keyword_rate"),
        },
        **comparison,
    }


# ─── Batch Reprocessing ─────────────────────────────────────────────────────


class ReprocessRequest(BaseModel):
    client_id: Optional[UUID] = None
    document_ids: Optional[List[UUID]] = None
    force: bool = False


@router.post(
    "/reprocess-documents",
    summary="Reprocess documents with new chunking strategy",
)
async def reprocess_documents(
    body: ReprocessRequest,
    _admin: None = Depends(verify_admin_access),
    db: Session = Depends(get_db),
) -> dict:
    """
    Reprocess selected documents with improved chunking and hybrid search.

    If force=true, all matching documents are re-chunked from scratch.
    If force=false, only unprocessed documents are queued.

    Each document costs ~$0.01-0.05 in embedding calls. Start with one
    test client before batch-processing everything.
    """
    from app.services.reprocess_service import reprocess_documents as _reprocess, _new_task

    if not body.client_id and not body.document_ids:
        raise HTTPException(
            status_code=400,
            detail="Provide either client_id or document_ids",
        )

    # Resolve document IDs
    if body.document_ids:
        docs = (
            db.query(Document)
            .filter(Document.id.in_(body.document_ids))
            .all()
        )
    else:
        query = db.query(Document).filter(Document.client_id == body.client_id)
        if not body.force:
            query = query.filter(Document.processed == False)  # noqa: E712
        docs = query.all()

    if not docs:
        return {
            "status": "no_documents",
            "documents_queued": 0,
            "message": "No documents matched the criteria",
        }

    doc_ids = [d.id for d in docs]
    task_id = _new_task(len(doc_ids))

    # Fire-and-forget background task
    asyncio.create_task(_reprocess(doc_ids, task_id))

    return {
        "status": "processing",
        "task_id": task_id,
        "documents_queued": len(doc_ids),
        "message": f"Reprocessing {len(doc_ids)} document(s) in background",
    }


@router.get(
    "/reprocess-status/{task_id}",
    summary="Check batch reprocessing progress",
)
async def reprocess_status(
    task_id: str,
    _admin: None = Depends(verify_admin_access),
) -> dict:
    from app.services.reprocess_service import get_task_status

    status = get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status
