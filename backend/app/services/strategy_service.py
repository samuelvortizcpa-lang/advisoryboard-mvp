"""
Tax Strategy Matrix service — filtering, status tracking, history.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.tax_strategy import TaxStrategy


# The only valid status values for a client_strategy_status row.
VALID_STATUSES = {"not_reviewed", "recommended", "implemented", "not_applicable", "declined"}

# The profile-flag columns on the Client model that strategies can reference.
PROFILE_FLAG_COLUMNS = [
    "has_business_entity",
    "has_real_estate",
    "is_real_estate_professional",
    "has_high_income",
    "has_estate_planning",
    "is_medical_professional",
    "has_retirement_plans",
    "has_investments",
    "has_employees",
]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_client_or_404(db: Session, client_id: UUID) -> Client:
    client = db.query(Client).filter(Client.id == client_id).first()
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


def _client_flags(client: Client) -> dict[str, bool]:
    """Read profile flag values from a Client ORM instance."""
    return {col: getattr(client, col, False) for col in PROFILE_FLAG_COLUMNS}


def _strategy_applicable(flags: dict[str, bool], required_flags: list[str]) -> bool:
    """A strategy is applicable if ALL its required_flags are True on the client."""
    return all(flags.get(f, False) for f in required_flags)


# ─── Main service functions ───────────────────────────────────────────────────


def get_strategies_for_client(
    db: Session,
    client_id: UUID,
    tax_year: int,
) -> dict:
    """
    Return applicable strategies for a client in a given tax year,
    grouped by category with existing status data joined in.
    """
    client = _get_client_or_404(db, client_id)
    flags = _client_flags(client)

    # All active strategies
    all_strategies = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .order_by(TaxStrategy.category, TaxStrategy.display_order)
        .all()
    )

    # Filter to applicable
    applicable = [s for s in all_strategies if _strategy_applicable(flags, s.required_flags or [])]

    if not applicable:
        return {
            "tax_year": tax_year,
            "client_id": str(client_id),
            "categories": [],
            "summary": {
                "total_applicable": 0,
                "total_reviewed": 0,
                "total_implemented": 0,
                "total_estimated_impact": 0.0,
            },
        }

    # Existing statuses for this client+year
    strategy_ids = [s.id for s in applicable]
    existing = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id == client_id,
            ClientStrategyStatus.tax_year == tax_year,
            ClientStrategyStatus.strategy_id.in_(strategy_ids),
        )
        .all()
    )
    status_map: dict[UUID, ClientStrategyStatus] = {e.strategy_id: e for e in existing}

    # Build grouped result
    categories: dict[str, list] = {}
    total_reviewed = 0
    total_implemented = 0
    total_impact = 0.0

    for strat in applicable:
        entry = status_map.get(strat.id)
        s_status = entry.status if entry else "not_reviewed"
        s_notes = entry.notes if entry else None
        s_impact = float(entry.estimated_impact) if entry and entry.estimated_impact is not None else None

        if s_status != "not_reviewed":
            total_reviewed += 1
        if s_status == "implemented":
            total_implemented += 1
        if s_impact is not None:
            total_impact += s_impact

        item = {
            "strategy": {
                "id": str(strat.id),
                "name": strat.name,
                "category": strat.category,
                "description": strat.description,
                "required_flags": strat.required_flags or [],
                "display_order": strat.display_order,
            },
            "status": s_status,
            "notes": s_notes,
            "estimated_impact": s_impact,
            "tax_year": tax_year,
        }
        categories.setdefault(strat.category, []).append(item)

    return {
        "tax_year": tax_year,
        "client_id": str(client_id),
        "categories": [
            {"category_name": cat, "strategies": items}
            for cat, items in categories.items()
        ],
        "summary": {
            "total_applicable": len(applicable),
            "total_reviewed": total_reviewed,
            "total_implemented": total_implemented,
            "total_estimated_impact": total_impact,
        },
    }


def update_strategy_status(
    db: Session,
    client_id: UUID,
    strategy_id: UUID,
    tax_year: int,
    new_status: str,
    notes: Optional[str] = None,
    estimated_impact: Optional[float] = None,
    user_id: Optional[str] = None,
) -> ClientStrategyStatus:
    """Upsert a single strategy status row."""
    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
        )

    # Verify client and strategy exist
    _get_client_or_404(db, client_id)
    strat = db.query(TaxStrategy).filter(TaxStrategy.id == strategy_id).first()
    if strat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

    now = datetime.now(timezone.utc)

    row = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id == client_id,
            ClientStrategyStatus.strategy_id == strategy_id,
            ClientStrategyStatus.tax_year == tax_year,
        )
        .first()
    )

    if row:
        row.status = new_status
        row.notes = notes
        row.estimated_impact = estimated_impact
        row.updated_by = user_id
        row.updated_at = now
    else:
        row = ClientStrategyStatus(
            client_id=client_id,
            strategy_id=strategy_id,
            tax_year=tax_year,
            status=new_status,
            notes=notes,
            estimated_impact=estimated_impact,
            updated_by=user_id,
            updated_at=now,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


def bulk_update_statuses(
    db: Session,
    client_id: UUID,
    updates: list[dict],
    user_id: Optional[str] = None,
) -> int:
    """Upsert multiple strategy status rows in a single transaction."""
    _get_client_or_404(db, client_id)
    now = datetime.now(timezone.utc)
    count = 0

    for item in updates:
        s = item["status"]
        if s not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{s}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
            )

        row = (
            db.query(ClientStrategyStatus)
            .filter(
                ClientStrategyStatus.client_id == client_id,
                ClientStrategyStatus.strategy_id == item["strategy_id"],
                ClientStrategyStatus.tax_year == item["tax_year"],
            )
            .first()
        )

        if row:
            row.status = s
            row.notes = item.get("notes")
            row.estimated_impact = item.get("estimated_impact")
            row.updated_by = user_id
            row.updated_at = now
        else:
            row = ClientStrategyStatus(
                client_id=client_id,
                strategy_id=item["strategy_id"],
                tax_year=item["tax_year"],
                status=s,
                notes=item.get("notes"),
                estimated_impact=item.get("estimated_impact"),
                updated_by=user_id,
                updated_at=now,
            )
            db.add(row)

        count += 1

    db.commit()
    return count


def get_strategy_history(db: Session, client_id: UUID) -> dict:
    """
    Return all strategy status data for a client across all years,
    structured for a year-over-year comparison grid.
    """
    client = _get_client_or_404(db, client_id)
    flags = _client_flags(client)

    # All applicable strategies (current profile)
    all_strategies = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .order_by(TaxStrategy.category, TaxStrategy.display_order)
        .all()
    )
    applicable = [s for s in all_strategies if _strategy_applicable(flags, s.required_flags or [])]
    applicable_ids = {s.id for s in applicable}

    # All existing status rows for this client
    all_statuses = (
        db.query(ClientStrategyStatus)
        .filter(ClientStrategyStatus.client_id == client_id)
        .all()
    )

    # Group statuses by strategy_id
    statuses_by_strategy: dict[UUID, list] = {}
    all_years: set[int] = set()
    for st in all_statuses:
        statuses_by_strategy.setdefault(st.strategy_id, []).append(st)
        all_years.add(st.tax_year)

    # Build strategy history list
    strategies_out = []
    for strat in applicable:
        year_statuses = []
        for st in statuses_by_strategy.get(strat.id, []):
            year_statuses.append({
                "tax_year": st.tax_year,
                "status": st.status,
                "notes": st.notes,
                "estimated_impact": float(st.estimated_impact) if st.estimated_impact is not None else None,
            })
        year_statuses.sort(key=lambda x: x["tax_year"])

        strategies_out.append({
            "strategy_id": str(strat.id),
            "name": strat.name,
            "category": strat.category,
            "statuses": year_statuses,
        })

    # Also include strategies that have status rows but are no longer "applicable"
    # (flags may have changed) — so history isn't lost.
    for strategy_id, sts in statuses_by_strategy.items():
        if strategy_id not in applicable_ids:
            strat = db.query(TaxStrategy).filter(TaxStrategy.id == strategy_id).first()
            if strat is None:
                continue
            year_statuses = []
            for st in sts:
                year_statuses.append({
                    "tax_year": st.tax_year,
                    "status": st.status,
                    "notes": st.notes,
                    "estimated_impact": float(st.estimated_impact) if st.estimated_impact is not None else None,
                })
            year_statuses.sort(key=lambda x: x["tax_year"])
            strategies_out.append({
                "strategy_id": str(strat.id),
                "name": strat.name,
                "category": strat.category,
                "statuses": year_statuses,
            })

    # Year summaries
    available_years = sorted(all_years)
    year_summaries = []
    for yr in available_years:
        yr_statuses = [st for st in all_statuses if st.tax_year == yr]
        reviewed = sum(1 for st in yr_statuses if st.status != "not_reviewed")
        implemented = sum(1 for st in yr_statuses if st.status == "implemented")
        impact = sum(
            float(st.estimated_impact) for st in yr_statuses
            if st.estimated_impact is not None
        )
        year_summaries.append({
            "tax_year": yr,
            "total_applicable": len(applicable),
            "total_reviewed": reviewed,
            "total_implemented": implemented,
            "total_estimated_impact": impact,
        })

    return {
        "strategies": strategies_out,
        "year_summaries": year_summaries,
        "available_years": available_years,
    }


def update_profile_flags(db: Session, client_id: UUID, flags_dict: dict) -> Client:
    """Partial update of tax strategy profile flags on a client."""
    client = _get_client_or_404(db, client_id)

    for key, value in flags_dict.items():
        if key in PROFILE_FLAG_COLUMNS and value is not None:
            setattr(client, key, value)

    client.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(client)
    return client
