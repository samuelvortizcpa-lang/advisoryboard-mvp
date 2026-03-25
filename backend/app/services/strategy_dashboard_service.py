"""
Cross-client strategy dashboard analytics.

Provides aggregate views of strategy coverage, adoption rates,
and unreviewed alerts across all of a user's accessible clients.
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.tax_strategy import TaxStrategy
from app.services.assignment_service import get_accessible_client_ids
from app.services.strategy_service import PROFILE_FLAG_COLUMNS, _strategy_applicable


def _accessible_clients_query(
    db: Session,
    user_id: str,
    org_id: UUID,
    org_role: str,
):
    """Return a query for Client rows the user can see."""
    q = db.query(Client).filter(Client.org_id == org_id)
    accessible_ids = get_accessible_client_ids(
        user_id, org_id, org_role == "admin", db
    )
    if accessible_ids is not None:
        q = q.filter(Client.id.in_(accessible_ids))
    return q


def _resolve_year(tax_year: Optional[int]) -> int:
    return tax_year if tax_year is not None else date.today().year


# ---------------------------------------------------------------------------
# 1. Overview
# ---------------------------------------------------------------------------


def get_strategy_overview(
    db: Session,
    user_id: str,
    org_id: UUID,
    org_role: str,
    tax_year: Optional[int] = None,
) -> dict:
    year = _resolve_year(tax_year)
    clients = _accessible_clients_query(db, user_id, org_id, org_role).all()

    if not clients:
        return {
            "total_clients": 0,
            "clients_reviewed": 0,
            "clients_unreviewed": 0,
            "total_implemented": 0,
            "total_estimated_impact": 0.0,
        }

    client_ids = [c.id for c in clients]

    all_statuses = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id.in_(client_ids),
            ClientStrategyStatus.tax_year == year,
        )
        .all()
    )

    # Which clients have at least one reviewed strategy?
    clients_with_review = set()
    total_implemented = 0
    total_impact = 0.0

    for s in all_statuses:
        if s.status != "not_reviewed":
            clients_with_review.add(s.client_id)
        if s.status == "implemented":
            total_implemented += 1
        if s.estimated_impact is not None:
            total_impact += float(s.estimated_impact)

    return {
        "total_clients": len(clients),
        "clients_reviewed": len(clients_with_review),
        "clients_unreviewed": len(clients) - len(clients_with_review),
        "total_implemented": total_implemented,
        "total_estimated_impact": total_impact,
    }


# ---------------------------------------------------------------------------
# 2. Client strategy summary
# ---------------------------------------------------------------------------


def get_client_strategy_summary(
    db: Session,
    user_id: str,
    org_id: UUID,
    org_role: str,
    tax_year: Optional[int] = None,
) -> list[dict]:
    year = _resolve_year(tax_year)
    clients = _accessible_clients_query(db, user_id, org_id, org_role).all()

    if not clients:
        return []

    # Load all active strategies once
    all_strategies = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .all()
    )

    # Pre-load all status rows for this year for all clients
    client_ids = [c.id for c in clients]
    all_statuses = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id.in_(client_ids),
            ClientStrategyStatus.tax_year == year,
        )
        .all()
    )
    # Group by client_id
    status_by_client: dict[UUID, list[ClientStrategyStatus]] = {}
    for s in all_statuses:
        status_by_client.setdefault(s.client_id, []).append(s)

    results = []
    for client in clients:
        # Determine applicable strategies
        flags = {col: getattr(client, col, False) for col in PROFILE_FLAG_COLUMNS}
        applicable = [
            s for s in all_strategies
            if _strategy_applicable(flags, s.required_flags or [])
        ]
        total_applicable = len(applicable)

        # Client's statuses for this year
        statuses = status_by_client.get(client.id, [])
        total_reviewed = sum(1 for s in statuses if s.status != "not_reviewed")
        total_implemented = sum(1 for s in statuses if s.status == "implemented")
        total_impact = sum(
            float(s.estimated_impact) for s in statuses
            if s.estimated_impact is not None
        )
        coverage_pct = (
            round(total_implemented / total_applicable * 100, 1)
            if total_applicable > 0 else 0.0
        )

        last_reviewed_at = None
        reviewed_statuses = [s for s in statuses if s.status != "not_reviewed" and s.updated_at]
        if reviewed_statuses:
            last_reviewed_at = max(s.updated_at for s in reviewed_statuses).isoformat()

        active_flags = [col for col in PROFILE_FLAG_COLUMNS if flags.get(col)]

        # client_type name via relationship
        ct_name = None
        if client.client_type:
            ct_name = client.client_type.name

        results.append({
            "client_id": str(client.id),
            "client_name": client.name,
            "client_type": ct_name,
            "active_flags": active_flags,
            "total_applicable": total_applicable,
            "total_reviewed": total_reviewed,
            "total_implemented": total_implemented,
            "total_estimated_impact": total_impact,
            "coverage_pct": coverage_pct,
            "last_reviewed_at": last_reviewed_at,
        })

    # Sort by coverage ascending (least coverage first)
    results.sort(key=lambda r: r["coverage_pct"])
    return results


# ---------------------------------------------------------------------------
# 3. Strategy adoption across clients
# ---------------------------------------------------------------------------


def get_strategy_adoption(
    db: Session,
    user_id: str,
    org_id: UUID,
    org_role: str,
    tax_year: Optional[int] = None,
) -> list[dict]:
    year = _resolve_year(tax_year)
    clients = _accessible_clients_query(db, user_id, org_id, org_role).all()

    if not clients:
        return []

    all_strategies = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .order_by(TaxStrategy.category, TaxStrategy.display_order)
        .all()
    )

    client_ids = [c.id for c in clients]
    all_statuses = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id.in_(client_ids),
            ClientStrategyStatus.tax_year == year,
        )
        .all()
    )
    # Map (strategy_id) → list of statuses
    status_by_strategy: dict[UUID, list[ClientStrategyStatus]] = {}
    for s in all_statuses:
        status_by_strategy.setdefault(s.strategy_id, []).append(s)

    # Pre-compute client flags
    client_flags = []
    for c in clients:
        flags = {col: getattr(c, col, False) for col in PROFILE_FLAG_COLUMNS}
        client_flags.append(flags)

    results = []
    for strat in all_strategies:
        # How many clients is this strategy applicable to?
        total_applicable = sum(
            1 for flags in client_flags
            if _strategy_applicable(flags, strat.required_flags or [])
        )
        if total_applicable == 0:
            continue

        statuses = status_by_strategy.get(strat.id, [])
        total_implemented = sum(1 for s in statuses if s.status == "implemented")
        total_recommended = sum(1 for s in statuses if s.status == "recommended")
        total_declined = sum(1 for s in statuses if s.status == "declined")
        adoption_rate = round(total_implemented / total_applicable * 100, 1)

        results.append({
            "strategy_id": str(strat.id),
            "strategy_name": strat.name,
            "category": strat.category,
            "total_applicable": total_applicable,
            "total_implemented": total_implemented,
            "total_recommended": total_recommended,
            "total_declined": total_declined,
            "adoption_rate": adoption_rate,
        })

    # Sort by adoption_rate ascending (least adopted first)
    results.sort(key=lambda r: r["adoption_rate"])
    return results


# ---------------------------------------------------------------------------
# 4. Unreviewed alerts
# ---------------------------------------------------------------------------


def get_unreviewed_alerts(
    db: Session,
    user_id: str,
    org_id: UUID,
    org_role: str,
    tax_year: Optional[int] = None,
) -> list[dict]:
    year = _resolve_year(tax_year)
    clients = _accessible_clients_query(db, user_id, org_id, org_role).all()

    if not clients:
        return []

    all_strategies = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .order_by(TaxStrategy.display_order)
        .all()
    )

    client_ids = [c.id for c in clients]

    # Load existing statuses for these clients+year
    existing = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id.in_(client_ids),
            ClientStrategyStatus.tax_year == year,
        )
        .all()
    )
    # Set of (client_id, strategy_id) that have been reviewed
    reviewed = {
        (s.client_id, s.strategy_id)
        for s in existing
        if s.status != "not_reviewed"
    }
    # Set of (client_id, strategy_id) explicitly marked not_reviewed
    explicit_not_reviewed = {
        (s.client_id, s.strategy_id)
        for s in existing
        if s.status == "not_reviewed"
    }

    alerts: list[dict] = []
    for client in clients:
        flags = {col: getattr(client, col, False) for col in PROFILE_FLAG_COLUMNS}
        for strat in all_strategies:
            if not _strategy_applicable(flags, strat.required_flags or []):
                continue
            key = (client.id, strat.id)
            # Unreviewed = either explicitly "not_reviewed" or no status row at all
            if key not in reviewed:
                alerts.append({
                    "client_id": str(client.id),
                    "client_name": client.name,
                    "strategy_id": str(strat.id),
                    "strategy_name": strat.name,
                    "category": strat.category,
                })

    # Limit to 20 (strategies with lower display_order = higher priority already sorted)
    return alerts[:20]
