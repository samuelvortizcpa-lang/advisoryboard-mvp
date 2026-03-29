"""
Token usage and subscription API endpoints.

Routes (all require Clerk JWT auth):
  GET  /api/usage/summary?days=30
  GET  /api/usage/clients/{client_id}?days=30
  GET  /api/usage/subscription
  GET  /api/usage/history          — paginated usage records
  GET  /api/usage/daily            — daily aggregated stats
  GET  /api/usage/by-client        — cost breakdown by client
  GET  /api/usage/export           — CSV download
"""

from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import cast, Date, func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.token_usage import TokenUsage
from app.schemas.usage import (
    ClientUsageResponse,
    DailyUsageResponse,
    ModelStats,
    UsageHistoryResponse,
    UsageRecordResponse,
)
from app.services.auth_context import AuthContext, get_auth
from app.services.subscription_service import (
    TIER_DEFAULTS,
    check_client_limit,
    check_document_limit,
    get_or_create_subscription,
    get_seat_info,
)
from app.services.token_tracking_service import get_usage_by_client, get_usage_summary

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usage_filter(query, auth: AuthContext):
    """
    Scope token usage queries to the org.  Admins see all org usage;
    non-admins see only their own.  Includes backward-compat fallback
    for records where org_id is NULL (pre-migration data).
    """
    if auth.org_role == "admin":
        return query.filter(
            or_(
                TokenUsage.org_id == auth.org_id,
                TokenUsage.user_id == auth.user_id,
            )
        )
    return query.filter(TokenUsage.user_id == auth.user_id)


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/usage/summary",
    summary="Get AI token usage summary for the authenticated user",
)
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict:
    return get_usage_summary(db, user_id=auth.user_id, days=days)


@router.get(
    "/usage/clients/{client_id}",
    summary="Get AI token usage for a specific client",
)
async def usage_by_client_endpoint(
    client_id: UUID,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict:
    return get_usage_by_client(db, user_id=auth.user_id, client_id=client_id, days=days)


@router.get(
    "/usage/subscription",
    summary="Get the authenticated user's subscription info",
)
async def subscription_info(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> dict:
    sub = get_or_create_subscription(db, auth.user_id)
    remaining = max(0, sub.strategic_queries_limit - sub.strategic_queries_used)

    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    client_info = check_client_limit(db, auth.user_id, org_id=auth.org_id)
    doc_info = check_document_limit(db, auth.user_id, org_id=auth.org_id)

    # Seat info (org-aware)
    if auth.org_id:
        seat_data = get_seat_info(auth.org_id, db)
    else:
        seat_data = None

    return {
        "tier": sub.tier,
        "strategic_queries_limit": sub.strategic_queries_limit,
        "strategic_queries_used": sub.strategic_queries_used,
        "strategic_queries_remaining": remaining,
        "billing_period_start": sub.billing_period_start.isoformat() if sub.billing_period_start else None,
        "billing_period_end": sub.billing_period_end.isoformat() if sub.billing_period_end else None,
        "max_clients": tier_config["max_clients"],
        "current_clients": client_info["current"],
        "max_documents": tier_config["max_documents"],
        "current_documents": doc_info["current"],
        "seats_included": seat_data["included"] if seat_data else 0,
        "seats_addon": seat_data["addon_purchased"] if seat_data else 0,
        "seats_total": seat_data["total_allowed"] if seat_data else 0,
        "seats_used": seat_data["current_used"] if seat_data else 0,
    }


# ---------------------------------------------------------------------------
# New analytics endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/usage/history",
    response_model=UsageHistoryResponse,
    summary="Paginated list of individual usage records",
)
async def usage_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    start_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD)"),
    model: Optional[str] = Query(None),
    endpoint: Optional[str] = Query(None),
    client_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> UsageHistoryResponse:
    query = (
        db.query(
            TokenUsage.id,
            TokenUsage.created_at,
            TokenUsage.endpoint,
            TokenUsage.model,
            TokenUsage.prompt_tokens,
            TokenUsage.completion_tokens,
            TokenUsage.total_tokens,
            TokenUsage.estimated_cost_usd,
            TokenUsage.client_id,
            Client.name.label("client_name"),
        )
        .outerjoin(Client, TokenUsage.client_id == Client.id)
    )
    query = _usage_filter(query, auth)

    if start_date:
        query = query.filter(TokenUsage.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        query = query.filter(TokenUsage.created_at < end_dt)
    if model:
        query = query.filter(TokenUsage.model == model)
    if endpoint:
        query = query.filter(TokenUsage.endpoint == endpoint)
    if client_id:
        query = query.filter(TokenUsage.client_id == client_id)

    total = query.count()
    total_pages = max(1, math.ceil(total / per_page))

    rows = (
        query
        .order_by(TokenUsage.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items = [
        UsageRecordResponse(
            id=r.id,
            created_at=r.created_at,
            endpoint=r.endpoint,
            model=r.model,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            total_tokens=r.total_tokens,
            estimated_cost=float(r.estimated_cost_usd),
            client_id=r.client_id,
            client_name=r.client_name,
        )
        for r in rows
    ]

    return UsageHistoryResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get(
    "/usage/daily",
    response_model=list[DailyUsageResponse],
    summary="Daily aggregated usage for charting",
)
async def usage_daily(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[DailyUsageResponse]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day_col = cast(TokenUsage.created_at, Date).label("day")

    query = (
        db.query(
            day_col,
            TokenUsage.model,
            func.count().label("queries"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("cost"),
        )
        .filter(TokenUsage.created_at >= since)
    )
    query = _usage_filter(query, auth)
    rows = query.group_by(day_col, TokenUsage.model).all()

    # Build lookup: date_str -> model -> stats
    daily: dict[str, dict[str, dict]] = {}
    for r in rows:
        d = r.day.isoformat() if isinstance(r.day, date) else str(r.day)
        daily.setdefault(d, {})
        daily[d][r.model] = {
            "queries": r.queries,
            "tokens": int(r.tokens),
            "cost": float(r.cost),
        }

    # Collect all models seen
    all_models = set()
    for models in daily.values():
        all_models.update(models.keys())

    # Generate continuous date range with zero-fills
    today = date.today()
    result: list[DailyUsageResponse] = []
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        model_data = daily.get(d, {})
        by_model = {
            m: ModelStats(
                queries=model_data.get(m, {}).get("queries", 0),
                tokens=model_data.get(m, {}).get("tokens", 0),
                cost=model_data.get(m, {}).get("cost", 0.0),
            )
            for m in all_models
        }
        result.append(
            DailyUsageResponse(
                date=d,
                total_queries=sum(s.queries for s in by_model.values()),
                total_tokens=sum(s.tokens for s in by_model.values()),
                total_cost=sum(s.cost for s in by_model.values()),
                by_model=by_model,
            )
        )

    return result


@router.get(
    "/usage/by-client",
    response_model=list[ClientUsageResponse],
    summary="Cost breakdown grouped by client",
)
async def usage_by_client_breakdown(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[ClientUsageResponse]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        db.query(
            TokenUsage.client_id,
            Client.name.label("client_name"),
            func.count().label("total_queries"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0).label("total_cost"),
            func.max(TokenUsage.created_at).label("last_query_at"),
        )
        .join(Client, TokenUsage.client_id == Client.id)
        .filter(
            TokenUsage.created_at >= since,
            TokenUsage.client_id.isnot(None),
        )
    )
    query = _usage_filter(query, auth)

    rows = (
        query
        .group_by(TokenUsage.client_id, Client.name)
        .order_by(func.sum(TokenUsage.estimated_cost_usd).desc())
        .all()
    )

    return [
        ClientUsageResponse(
            client_id=r.client_id,
            client_name=r.client_name,
            total_queries=r.total_queries,
            total_tokens=int(r.total_tokens),
            total_cost=float(r.total_cost),
            last_query_at=r.last_query_at,
        )
        for r in rows
    ]


@router.get(
    "/usage/export",
    summary="CSV export of usage history",
)
async def usage_export(
    start_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date string (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> StreamingResponse:
    query = (
        db.query(
            TokenUsage.created_at,
            TokenUsage.endpoint,
            TokenUsage.model,
            TokenUsage.prompt_tokens,
            TokenUsage.completion_tokens,
            TokenUsage.total_tokens,
            TokenUsage.estimated_cost_usd,
            Client.name.label("client_name"),
        )
        .outerjoin(Client, TokenUsage.client_id == Client.id)
    )
    query = _usage_filter(query, auth)

    if start_date:
        query = query.filter(TokenUsage.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        query = query.filter(TokenUsage.created_at < end_dt)

    rows = query.order_by(TokenUsage.created_at.desc()).limit(10000).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Date", "Endpoint", "Model", "Prompt Tokens",
        "Completion Tokens", "Total Tokens", "Cost", "Client Name",
    ])
    for r in rows:
        writer.writerow([
            r.created_at.isoformat(),
            r.endpoint or "",
            r.model,
            r.prompt_tokens,
            r.completion_tokens,
            r.total_tokens,
            f"{float(r.estimated_cost_usd):.6f}",
            r.client_name or "",
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=usage_export.csv"},
    )
