"""
Token usage and subscription API endpoints.

Routes (all require Clerk JWT auth):
  GET  /api/usage/summary?days=30
  GET  /api/usage/clients/{client_id}?days=30
  GET  /api/usage/subscription
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.services import user_service
from app.services.subscription_service import get_or_create_subscription
from app.services.token_tracking_service import get_usage_by_client, get_usage_summary

router = APIRouter()


@router.get(
    "/usage/summary",
    summary="Get AI token usage summary for the authenticated user",
)
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> dict:
    user = user_service.get_or_create_user(db, current_user)
    return get_usage_summary(db, user_id=user.clerk_id, days=days)


@router.get(
    "/usage/clients/{client_id}",
    summary="Get AI token usage for a specific client",
)
async def usage_by_client(
    client_id: UUID,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> dict:
    user = user_service.get_or_create_user(db, current_user)
    return get_usage_by_client(db, user_id=user.clerk_id, client_id=client_id, days=days)


@router.get(
    "/usage/subscription",
    summary="Get the authenticated user's subscription info",
)
async def subscription_info(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> dict:
    user = user_service.get_or_create_user(db, current_user)
    sub = get_or_create_subscription(db, user.clerk_id)
    remaining = max(0, sub.strategic_queries_limit - sub.strategic_queries_used)
    return {
        "tier": sub.tier,
        "strategic_queries_limit": sub.strategic_queries_limit,
        "strategic_queries_used": sub.strategic_queries_used,
        "strategic_queries_remaining": remaining,
        "billing_period_start": sub.billing_period_start.isoformat() if sub.billing_period_start else None,
        "billing_period_end": sub.billing_period_end.isoformat() if sub.billing_period_end else None,
    }
