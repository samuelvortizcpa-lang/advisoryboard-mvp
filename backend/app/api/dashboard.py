"""
Dashboard endpoints — aggregate counts and summary data for the frontend.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import date, datetime, timedelta, timezone
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.document import Document
from app.models.organization_member import OrganizationMember
from app.models.tax_strategy import TaxStrategy
from app.models.token_usage import TokenUsage
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.services.assignment_service import get_accessible_client_ids
from app.services.auth_context import AuthContext, get_auth
from app.services.strategy_service import PROFILE_FLAG_COLUMNS, _strategy_applicable
from app.services.subscription_service import (
    TIER_DEFAULTS,
    get_or_create_subscription,
    get_seat_info,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── TTL cache for dashboard summary ──────────────────────────────────────────
_DASHBOARD_CACHE_TTL = 30  # seconds
_dashboard_cache: dict[str, tuple[float, Any]] = {}


# ─── Legacy endpoint (kept for backward compat) ──────────────────────────────


class DashboardStatsResponse(BaseModel):
    clients: int
    documents: int
    interactions: int


@router.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse,
    summary="Aggregate counts for the current user's dashboard",
)
async def dashboard_stats(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DashboardStatsResponse:
    client_count = (
        db.query(Client)
        .filter(Client.org_id == auth.org_id)
        .count()
    )
    document_count = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(Client.org_id == auth.org_id)
        .count()
    )
    interaction_count = (
        db.query(ActionItem)
        .join(Client, ActionItem.client_id == Client.id)
        .filter(Client.org_id == auth.org_id)
        .count()
    )
    return DashboardStatsResponse(
        clients=client_count,
        documents=document_count,
        interactions=interaction_count,
    )


# ─── Summary endpoint schemas ─────────────────────────────────────────────────


class CountWithLimit(BaseModel):
    count: int
    limit: Optional[int] = None


class ActionItemStats(BaseModel):
    pending: int
    overdue: int


class QueryStats(BaseModel):
    used: int
    limit: int


class StatsBlock(BaseModel):
    clients: CountWithLimit
    action_items: ActionItemStats
    documents: CountWithLimit
    ai_queries: QueryStats


class ActivityPoint(BaseModel):
    date: str
    queries: int


class QueryTypeCount(BaseModel):
    type: str
    count: int


class AttentionItem(BaseModel):
    id: str
    description: str
    client_name: str
    client_id: str
    due_date: Optional[str] = None
    priority: str  # critical, warning, info
    overdue_days: Optional[int] = None


class RecentClient(BaseModel):
    id: str
    name: str
    document_count: int
    action_item_count: int
    last_activity: str


class TeamMember(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    queries_used: int
    last_active: Optional[str] = None


class PlanInfo(BaseModel):
    tier: str
    billing_interval: Optional[str] = None
    seats_used: Optional[int] = None
    seats_total: Optional[int] = None


class DashboardSummary(BaseModel):
    stats: StatsBlock
    activity_chart: List[ActivityPoint]
    query_distribution: List[QueryTypeCount]
    attention_items: List[AttentionItem]
    recent_clients: List[RecentClient]
    team_members: Optional[List[TeamMember]] = None
    plan: PlanInfo


# ─── Helpers ──────────────────────────────────────────────────────────────────


# Map raw endpoint values to human-friendly labels
_ENDPOINT_LABELS = {
    "chat": "Quick Lookup",
    "chat_strategic": "Deep Analysis",
    "brief": "Brief",
    "action_items": "Action Items",
    "classify": "Other",
}


def _usage_filter(query, auth: AuthContext):
    """Scope token usage: admins see all org usage, members see only their own."""
    if auth.org_role == "admin":
        return query.filter(
            or_(
                TokenUsage.org_id == auth.org_id,
                TokenUsage.user_id == auth.user_id,
            )
        )
    return query.filter(TokenUsage.user_id == auth.user_id)


def _billing_interval(sub: UserSubscription) -> Optional[str]:
    """Infer billing interval from billing period length."""
    if sub.billing_period_start and sub.billing_period_end:
        delta = (sub.billing_period_end - sub.billing_period_start).days
        return "annual" if delta > 60 else "monthly"
    return None


# ─── Summary endpoint ─────────────────────────────────────────────────────────


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummary,
    summary="Aggregated dashboard data in a single call",
)
async def dashboard_summary(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> DashboardSummary:
    # Check TTL cache — avoid recomputing on rapid navigation
    cache_key = f"{auth.org_id}:{auth.user_id}:{days}"
    cached = _dashboard_cache.get(cache_key)
    if cached is not None:
        ts, data = cached
        if _time.monotonic() - ts < _DASHBOARD_CACHE_TTL:
            return data

    result = _build_dashboard_summary(days, db, auth)
    _dashboard_cache[cache_key] = (_time.monotonic(), result)
    return result


def _build_dashboard_summary(
    days: int,
    db: Session,
    auth: AuthContext,
) -> DashboardSummary:
    now = datetime.now(timezone.utc)
    today = date.today()
    cutoff = now - timedelta(days=days)

    # ── Stats ─────────────────────────────────────────────────────────────

    sub = get_or_create_subscription(db, auth.user_id, org_id=auth.org_id)
    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])

    # ── Assignment-based scoping (opt-in) ──────────────────────────────
    # When the org has client assignments, non-admin members only see
    # data for their assigned clients.  None = no filtering (admin or
    # no assignments yet).
    accessible_ids = get_accessible_client_ids(
        auth.user_id, auth.org_id, auth.org_role == "admin", db
    )

    client_q = db.query(func.count(Client.id)).filter(Client.org_id == auth.org_id)
    if accessible_ids is not None:
        client_q = client_q.filter(Client.id.in_(accessible_ids))
    client_count = client_q.scalar() or 0

    doc_q = (
        db.query(func.count(Document.id))
        .join(Client, Document.client_id == Client.id)
        .filter(Client.org_id == auth.org_id)
    )
    if accessible_ids is not None:
        doc_q = doc_q.filter(Client.id.in_(accessible_ids))
    doc_count = doc_q.scalar() or 0

    pending_q = (
        db.query(func.count(ActionItem.id))
        .join(Client, ActionItem.client_id == Client.id)
        .filter(Client.org_id == auth.org_id, ActionItem.status == "pending")
    )
    if accessible_ids is not None:
        pending_q = pending_q.filter(Client.id.in_(accessible_ids))
    pending_count = pending_q.scalar() or 0

    overdue_q = (
        db.query(func.count(ActionItem.id))
        .join(Client, ActionItem.client_id == Client.id)
        .filter(
            Client.org_id == auth.org_id,
            ActionItem.status == "pending",
            ActionItem.due_date < today,
        )
    )
    if accessible_ids is not None:
        overdue_q = overdue_q.filter(Client.id.in_(accessible_ids))
    overdue_count = overdue_q.scalar() or 0

    stats = StatsBlock(
        clients=CountWithLimit(count=client_count, limit=tier_config.get("max_clients")),
        action_items=ActionItemStats(pending=pending_count, overdue=overdue_count),
        documents=CountWithLimit(count=doc_count, limit=tier_config.get("max_documents")),
        ai_queries=QueryStats(
            used=sub.strategic_queries_used,
            limit=sub.strategic_queries_limit,
        ),
    )

    # ── Activity chart ────────────────────────────────────────────────────

    usage_q = db.query(
        func.date(TokenUsage.created_at).label("day"),
        func.count(TokenUsage.id).label("cnt"),
    ).filter(TokenUsage.created_at >= cutoff)
    usage_q = _usage_filter(usage_q, auth)
    usage_rows = (
        usage_q
        .group_by(func.date(TokenUsage.created_at))
        .order_by(func.date(TokenUsage.created_at))
        .all()
    )

    # Fill in missing days with zero
    day_map = {str(r.day): r.cnt for r in usage_rows}
    activity_chart: list[ActivityPoint] = []
    for i in range(days):
        d = (today - timedelta(days=days - 1 - i)).isoformat()
        activity_chart.append(ActivityPoint(date=d, queries=day_map.get(d, 0)))

    # ── Query distribution ────────────────────────────────────────────────

    dist_q = db.query(
        TokenUsage.endpoint,
        func.count(TokenUsage.id).label("cnt"),
    ).filter(TokenUsage.created_at >= cutoff)
    dist_q = _usage_filter(dist_q, auth)
    dist_rows = dist_q.group_by(TokenUsage.endpoint).all()

    query_distribution: list[QueryTypeCount] = []
    for row in dist_rows:
        label = _ENDPOINT_LABELS.get(row.endpoint or "", "Other")
        query_distribution.append(QueryTypeCount(type=label, count=row.cnt))

    # Merge duplicates (multiple raw endpoints → same label)
    merged: dict[str, int] = {}
    for qd in query_distribution:
        merged[qd.type] = merged.get(qd.type, 0) + qd.count
    query_distribution = [QueryTypeCount(type=t, count=c) for t, c in merged.items()]

    # ── Attention items (pending action items, prioritized) ───────────────

    attention_q = (
        db.query(ActionItem, Client.name)
        .join(Client, ActionItem.client_id == Client.id)
        .filter(
            Client.org_id == auth.org_id,
            ActionItem.status == "pending",
        )
    )
    if accessible_ids is not None:
        attention_q = attention_q.filter(Client.id.in_(accessible_ids))
    attention_rows = (
        attention_q
        .order_by(
            ActionItem.due_date.asc().nullslast(),
            ActionItem.created_at.desc(),
        )
        .limit(5)
        .all()
    )

    attention_items: list[AttentionItem] = []
    for ai, client_name in attention_rows:
        overdue_d: int | None = None
        if ai.due_date and ai.due_date < today:
            overdue_d = (today - ai.due_date).days
            priority = "critical"
        elif ai.due_date and (ai.due_date - today).days <= 7:
            priority = "warning"
        else:
            priority = "info"

        attention_items.append(AttentionItem(
            id=str(ai.id),
            description=ai.text or "",
            client_name=client_name or "",
            client_id=str(ai.client_id),
            due_date=ai.due_date.isoformat() if ai.due_date else None,
            priority=priority,
            overdue_days=overdue_d,
        ))

    # ── Recent clients ────────────────────────────────────────────────────

    doc_sub = (
        db.query(
            Document.client_id,
            func.count(Document.id).label("doc_cnt"),
        )
        .group_by(Document.client_id)
        .subquery()
    )

    ai_sub = (
        db.query(
            ActionItem.client_id,
            func.count(ActionItem.id).label("ai_cnt"),
        )
        .group_by(ActionItem.client_id)
        .subquery()
    )

    recent_q = (
        db.query(
            Client,
            func.coalesce(doc_sub.c.doc_cnt, 0).label("doc_count"),
            func.coalesce(ai_sub.c.ai_cnt, 0).label("ai_count"),
        )
        .outerjoin(doc_sub, Client.id == doc_sub.c.client_id)
        .outerjoin(ai_sub, Client.id == ai_sub.c.client_id)
        .filter(Client.org_id == auth.org_id)
    )
    if accessible_ids is not None:
        recent_q = recent_q.filter(Client.id.in_(accessible_ids))
    recent_rows = (
        recent_q
        .order_by(Client.updated_at.desc())
        .limit(5)
        .all()
    )

    recent_clients: list[RecentClient] = []
    for client, doc_c, ai_c in recent_rows:
        recent_clients.append(RecentClient(
            id=str(client.id),
            name=client.name,
            document_count=doc_c,
            action_item_count=ai_c,
            last_activity=client.updated_at.isoformat() if client.updated_at else client.created_at.isoformat(),
        ))

    # ── Team members (org accounts only) ──────────────────────────────────

    team_members: list[TeamMember] | None = None
    if not auth.is_personal_org:
        members = (
            db.query(OrganizationMember, User)
            .outerjoin(User, OrganizationMember.user_id == User.clerk_id)
            .filter(
                OrganizationMember.org_id == auth.org_id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
            .all()
        )

        # Batch query: usage counts + last activity for all members at once
        member_ids = [m.user_id for m, _ in members]
        usage_stats = (
            db.query(
                TokenUsage.user_id,
                func.count(TokenUsage.id).label("cnt"),
                func.max(TokenUsage.created_at).label("last_active"),
            )
            .filter(TokenUsage.user_id.in_(member_ids))
            .group_by(TokenUsage.user_id)
            .all()
        ) if member_ids else []

        # Split into period counts and overall last-active
        period_counts = {}
        last_active_map = {}
        for row in usage_stats:
            last_active_map[row.user_id] = row.last_active

        # Separate query for period-scoped counts
        period_stats = (
            db.query(
                TokenUsage.user_id,
                func.count(TokenUsage.id).label("cnt"),
            )
            .filter(
                TokenUsage.user_id.in_(member_ids),
                TokenUsage.created_at >= cutoff,
            )
            .group_by(TokenUsage.user_id)
            .all()
        ) if member_ids else []
        for row in period_stats:
            period_counts[row.user_id] = row.cnt

        team_members = []
        for mem, usr in members:
            name = ""
            email = ""
            if usr:
                parts = [usr.first_name, usr.last_name]
                name = " ".join(p for p in parts if p) or ""
                email = usr.email or ""

            last_q = last_active_map.get(mem.user_id)
            team_members.append(TeamMember(
                user_id=mem.user_id,
                name=name or mem.user_id,
                email=email,
                role=mem.role,
                queries_used=period_counts.get(mem.user_id, 0),
                last_active=last_q.isoformat() if last_q else None,
            ))

    # ── Plan ──────────────────────────────────────────────────────────────

    seat_data = get_seat_info(auth.org_id, db) if auth.org_id else None

    plan = PlanInfo(
        tier=sub.tier,
        billing_interval=_billing_interval(sub),
        seats_used=seat_data["current_used"] if seat_data else None,
        seats_total=seat_data["total_allowed"] if seat_data else None,
    )

    return DashboardSummary(
        stats=stats,
        activity_chart=activity_chart,
        query_distribution=query_distribution,
        attention_items=attention_items,
        recent_clients=recent_clients,
        team_members=team_members,
        plan=plan,
    )


# ─── Priority feed endpoint ──────────────────────────────────────────────────


class PriorityFeedItem(BaseModel):
    type: str  # action_item, strategy_alert, inactive_client
    priority: str  # critical, warning, info, low
    title: str
    subtitle: str
    client_id: Optional[str] = None
    link: str


_PRIORITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "low": 3}


@router.get(
    "/dashboard/priority-feed",
    response_model=List[PriorityFeedItem],
    summary="Unified priority feed merging action items, strategy alerts, and inactive clients",
)
async def priority_feed(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[PriorityFeedItem]:
    today = date.today()

    # ── Scoping ────────────────────────────────────────────────────────────
    accessible_ids = get_accessible_client_ids(
        auth.user_id, auth.org_id, auth.org_role == "admin", db
    )

    def scoped_client_filter(query):
        query = query.filter(Client.org_id == auth.org_id)
        if accessible_ids is not None:
            query = query.filter(Client.id.in_(accessible_ids))
        return query

    items: list[PriorityFeedItem] = []

    # ── Source 1: overdue / upcoming action items ──────────────────────────
    action_q = (
        db.query(ActionItem, Client.name)
        .join(Client, ActionItem.client_id == Client.id)
        .filter(
            Client.org_id == auth.org_id,
            ActionItem.status == "pending",
        )
    )
    if accessible_ids is not None:
        action_q = action_q.filter(Client.id.in_(accessible_ids))

    # Only include overdue or due within 7 days
    seven_days = today + timedelta(days=7)
    action_q = action_q.filter(
        ActionItem.due_date.isnot(None),
        ActionItem.due_date <= seven_days,
    )
    action_rows = (
        action_q
        .order_by(ActionItem.due_date.asc())
        .limit(10)
        .all()
    )

    for ai, client_name in action_rows:
        if ai.due_date < today:
            overdue_d = (today - ai.due_date).days
            priority = "critical"
            subtitle = f"{client_name} — Overdue by {overdue_d} day{'s' if overdue_d != 1 else ''}"
        else:
            diff = (ai.due_date - today).days
            priority = "warning"
            if diff == 0:
                subtitle = f"{client_name} — Due today"
            elif diff == 1:
                subtitle = f"{client_name} — Due tomorrow"
            else:
                subtitle = f"{client_name} — Due in {diff} days"

        items.append(PriorityFeedItem(
            type="action_item",
            priority=priority,
            title=ai.text or "Untitled action item",
            subtitle=subtitle,
            client_id=str(ai.client_id),
            link="/dashboard/action-items",
        ))

    # ── Source 2: unreviewed strategy alerts ───────────────────────────────
    try:
        year = today.year
        clients_for_strat = scoped_client_filter(db.query(Client)).all()

        if clients_for_strat:
            client_ids = [c.id for c in clients_for_strat]
            all_strategies = (
                db.query(TaxStrategy)
                .filter(TaxStrategy.is_active == True)  # noqa: E712
                .all()
            )

            existing_statuses = (
                db.query(ClientStrategyStatus)
                .filter(
                    ClientStrategyStatus.client_id.in_(client_ids),
                    ClientStrategyStatus.tax_year == year,
                )
                .all()
            )
            reviewed_keys = {
                (s.client_id, s.strategy_id)
                for s in existing_statuses
                if s.status != "not_reviewed"
            }

            # Count unreviewed strategies per client
            unreviewed_counts: dict[str, tuple[str, int]] = {}  # client_id -> (name, count)
            for client in clients_for_strat:
                flags = {col: getattr(client, col, False) for col in PROFILE_FLAG_COLUMNS}
                count = 0
                for strat in all_strategies:
                    if not _strategy_applicable(flags, strat.required_flags or []):
                        continue
                    if (client.id, strat.id) not in reviewed_keys:
                        count += 1
                if count > 0:
                    unreviewed_counts[str(client.id)] = (client.name, count)

            # Sort by count descending, take top entries
            for cid, (cname, cnt) in sorted(
                unreviewed_counts.items(), key=lambda x: -x[1]
            )[:5]:
                items.append(PriorityFeedItem(
                    type="strategy_alert",
                    priority="info",
                    title=f"{cname} has unreviewed strategies",
                    subtitle=f"{cnt} strateg{'y' if cnt == 1 else 'ies'} pending review",
                    client_id=cid,
                    link=f"/dashboard/clients/{cid}?tab=strategies",
                ))
    except Exception:
        logger.debug("Strategy alert query skipped (tables may not exist)", exc_info=True)

    # ── Source 3: inactive clients (no update in 30+ days) ─────────────────
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
    inactive_q = scoped_client_filter(
        db.query(Client).filter(Client.updated_at < cutoff_date)
    )
    inactive_clients = inactive_q.order_by(Client.updated_at.asc()).limit(5).all()

    for client in inactive_clients:
        days_inactive = (datetime.now(timezone.utc) - client.updated_at).days
        items.append(PriorityFeedItem(
            type="inactive_client",
            priority="low",
            title=f"{client.name} — no activity in {days_inactive} days",
            subtitle="Consider scheduling a check-in",
            client_id=str(client.id),
            link=f"/dashboard/clients/{client.id}",
        ))

    # ── Merge & sort by priority, limit to 10 ─────────────────────────────
    items.sort(key=lambda x: _PRIORITY_ORDER.get(x.priority, 99))
    return items[:10]


# ─── Revenue impact endpoint ─────────────────────────────────────────────────


class MonthAmount(BaseModel):
    month: str
    amount: float


class RevenueImpact(BaseModel):
    total_estimated_savings: float
    strategies_implemented: int
    clients_impacted: int
    monthly_trend: List[MonthAmount]


_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@router.get(
    "/dashboard/revenue-impact",
    response_model=RevenueImpact,
    summary="Revenue impact from implemented strategies for a given year",
)
async def revenue_impact(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> RevenueImpact:
    if year is None:
        year = date.today().year

    accessible_ids = get_accessible_client_ids(
        auth.user_id, auth.org_id, auth.org_role == "admin", db
    )

    # Get all clients the user can see
    client_q = db.query(Client.id).filter(Client.org_id == auth.org_id)
    if accessible_ids is not None:
        client_q = client_q.filter(Client.id.in_(accessible_ids))
    client_ids = [row[0] for row in client_q.all()]

    if not client_ids:
        return RevenueImpact(
            total_estimated_savings=0,
            strategies_implemented=0,
            clients_impacted=0,
            monthly_trend=[MonthAmount(month=m, amount=0) for m in _MONTH_NAMES[-6:]],
        )

    # Get all implemented statuses for the year
    implemented = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id.in_(client_ids),
            ClientStrategyStatus.tax_year == year,
            ClientStrategyStatus.status == "implemented",
        )
        .all()
    )

    total_savings = 0.0
    clients_set: set[UUID] = set()
    # Track cumulative savings by month (based on updated_at)
    month_savings: dict[int, float] = {}

    for s in implemented:
        impact = float(s.estimated_impact) if s.estimated_impact is not None else 0.0
        total_savings += impact
        clients_set.add(s.client_id)
        if s.updated_at:
            m = s.updated_at.month
            month_savings[m] = month_savings.get(m, 0) + impact

    # Build 6-month cumulative trend ending at current month
    today = date.today()
    current_month = today.month
    trend: list[MonthAmount] = []
    cumulative = 0.0
    # Start from 5 months ago
    for offset in range(5, -1, -1):
        m = current_month - offset
        if m <= 0:
            m += 12
        cumulative += month_savings.get(m, 0)
        trend.append(MonthAmount(month=_MONTH_NAMES[m - 1], amount=round(cumulative, 2)))

    return RevenueImpact(
        total_estimated_savings=round(total_savings, 2),
        strategies_implemented=len(implemented),
        clients_impacted=len(clients_set),
        monthly_trend=trend,
    )
