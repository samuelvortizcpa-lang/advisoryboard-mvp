"""
Tax Strategy Matrix service — filtering, status tracking, history,
and strategy-implementation-task materialization.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.client_assignment import ClientAssignment
from app.models.client_strategy_status import ClientStrategyStatus
from app.models.strategy_implementation_task import StrategyImplementationTask
from app.models.tax_strategy import TaxStrategy

logger = logging.getLogger(__name__)


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

    old_status = row.status if row else "not_reviewed"

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

    # Materialize implementation tasks on transition INTO 'recommended'
    if new_status == "recommended" and old_status != "recommended":
        materialize_implementation_tasks(
            db,
            client_id=client_id,
            strategy_id=strategy_id,
            tax_year=tax_year,
            user_id=user_id or "",
        )

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

    materialize_queue: list[dict] = []

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

        old_status = row.status if row else "not_reviewed"

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

        if s == "recommended" and old_status != "recommended":
            materialize_queue.append({
                "strategy_id": item["strategy_id"],
                "tax_year": item["tax_year"],
            })

        count += 1

    db.commit()

    for mq in materialize_queue:
        materialize_implementation_tasks(
            db,
            client_id=client_id,
            strategy_id=mq["strategy_id"],
            tax_year=mq["tax_year"],
            user_id=user_id or "",
        )

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


# ─── Implementation task helpers ──────────────────────────────────────────


def _resolve_primary_cpa_assignment(
    db: Session, client_id: UUID
) -> Optional[Tuple[str, str]]:
    """Return (user_id, display_name) for the first assignment on this client, or None."""
    assignment = (
        db.query(ClientAssignment)
        .filter(ClientAssignment.client_id == client_id)
        .first()
    )
    if assignment is None:
        return None
    # ClientAssignment stores Clerk user_id; display name isn't on this model,
    # so we return user_id for both fields (the API layer can resolve display name).
    return (assignment.user_id, assignment.user_id)


# ─── Implementation task service functions ────────────────────────────────


def materialize_implementation_tasks(
    db: Session,
    *,
    client_id: UUID,
    strategy_id: UUID,
    tax_year: int,
    user_id: str,
) -> int:
    """Generate action_items from strategy_implementation_tasks for a (client, strategy, year) bundle.

    Idempotent: skips templates that already have a corresponding action_items row
    for this client_strategy_status. Returns the count of NEW tasks created.
    """
    # Look up the client_strategy_status row
    css = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id == client_id,
            ClientStrategyStatus.strategy_id == strategy_id,
            ClientStrategyStatus.tax_year == tax_year,
        )
        .first()
    )
    if css is None:
        raise ValueError(
            f"No client_strategy_status for client={client_id}, "
            f"strategy={strategy_id}, year={tax_year}"
        )

    # Load active templates ordered by display_order
    templates = (
        db.query(StrategyImplementationTask)
        .filter(
            StrategyImplementationTask.strategy_id == strategy_id,
            StrategyImplementationTask.is_active == True,  # noqa: E712
        )
        .order_by(StrategyImplementationTask.display_order)
        .all()
    )

    if not templates:
        return 0

    # Find existing non-cancelled action_items for this css to enforce idempotency
    existing_template_ids = set(
        row[0]
        for row in db.query(ActionItem.strategy_implementation_task_id)
        .filter(
            ActionItem.client_strategy_status_id == css.id,
            ActionItem.strategy_implementation_task_id.isnot(None),
            ActionItem.status != "cancelled",
        )
        .all()
    )

    # Resolve primary CPA assignment for owner_role='cpa' tasks
    cpa_info = _resolve_primary_cpa_assignment(db, client_id)
    today = date.today()

    created_count = 0
    for tmpl in templates:
        if tmpl.id in existing_template_ids:
            continue

        assigned_to = None
        assigned_to_name = None
        if tmpl.default_owner_role == "cpa" and cpa_info:
            assigned_to, assigned_to_name = cpa_info

        item = ActionItem(
            client_id=client_id,
            text=tmpl.task_name,
            status="pending",
            priority="medium",
            due_date=today + timedelta(days=tmpl.default_lead_days),
            owner_role=tmpl.default_owner_role,
            owner_external_label=tmpl.default_owner_external_label,
            strategy_implementation_task_id=tmpl.id,
            client_strategy_status_id=css.id,
            assigned_to=assigned_to,
            assigned_to_name=assigned_to_name,
            source="strategy_implementation",
            created_by=user_id,
        )
        db.add(item)
        created_count += 1

    if created_count > 0:
        db.flush()

        # Write journal entry
        strategy = db.query(TaxStrategy).filter(TaxStrategy.id == strategy_id).first()
        strategy_name = strategy.name if strategy else str(strategy_id)

        from app.services.journal_service import create_auto_entry

        create_auto_entry(
            db=db,
            client_id=client_id,
            user_id=user_id,
            entry_type="system",
            category="strategy",
            title=f"Generated {created_count} implementation tasks for {strategy_name}",
            source_type="system",
            metadata={
                "strategy_id": str(strategy_id),
                "tax_year": tax_year,
                "task_count": created_count,
            },
        )

    return created_count


def get_implementation_progress(
    db: Session,
    *,
    client_id: UUID,
    strategy_id: UUID,
    tax_year: int,
) -> dict:
    """Return implementation progress for a (client, strategy, year) bundle."""
    css = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id == client_id,
            ClientStrategyStatus.strategy_id == strategy_id,
            ClientStrategyStatus.tax_year == tax_year,
        )
        .first()
    )

    empty = {
        "total": 0,
        "completed": 0,
        "by_owner_role": {
            "cpa": {"total": 0, "completed": 0},
            "client": {"total": 0, "completed": 0},
            "third_party": {"total": 0, "completed": 0},
        },
        "tasks": [],
    }

    if css is None:
        return empty

    # Join with template to get display_order
    rows = (
        db.query(ActionItem, StrategyImplementationTask.display_order)
        .join(
            StrategyImplementationTask,
            ActionItem.strategy_implementation_task_id == StrategyImplementationTask.id,
        )
        .filter(ActionItem.client_strategy_status_id == css.id)
        .order_by(StrategyImplementationTask.display_order)
        .all()
    )

    if not rows:
        return empty

    total = len(rows)
    completed = sum(1 for item, _ in rows if item.status == "completed")

    by_role: dict[str, dict[str, int]] = {
        "cpa": {"total": 0, "completed": 0},
        "client": {"total": 0, "completed": 0},
        "third_party": {"total": 0, "completed": 0},
    }

    tasks = []
    for item, display_order in rows:
        role = item.owner_role or "cpa"
        if role in by_role:
            by_role[role]["total"] += 1
            if item.status == "completed":
                by_role[role]["completed"] += 1

        tasks.append({
            "id": item.id,
            "task_name": item.text,
            "owner_role": role,
            "owner_external_label": item.owner_external_label,
            "status": item.status,
            "due_date": item.due_date,
            "completed_at": item.completed_at,
            "display_order": display_order,
        })

    return {
        "total": total,
        "completed": completed,
        "by_owner_role": by_role,
        "tasks": tasks,
    }


def archive_implementation_tasks(
    db: Session,
    *,
    client_id: UUID,
    strategy_id: UUID,
    tax_year: int,
    user_id: str,
) -> int:
    """Soft-archive materialized implementation tasks by setting status to 'cancelled'.

    Skips rows already cancelled or completed. Idempotent.
    """
    css = (
        db.query(ClientStrategyStatus)
        .filter(
            ClientStrategyStatus.client_id == client_id,
            ClientStrategyStatus.strategy_id == strategy_id,
            ClientStrategyStatus.tax_year == tax_year,
        )
        .first()
    )
    if css is None:
        return 0

    items = (
        db.query(ActionItem)
        .filter(
            ActionItem.client_strategy_status_id == css.id,
            ActionItem.status.notin_(["cancelled", "completed"]),
        )
        .all()
    )

    count = len(items)
    for item in items:
        item.status = "cancelled"

    if count > 0:
        db.flush()

        strategy = db.query(TaxStrategy).filter(TaxStrategy.id == strategy_id).first()
        strategy_name = strategy.name if strategy else str(strategy_id)

        from app.services.journal_service import create_auto_entry

        create_auto_entry(
            db=db,
            client_id=client_id,
            user_id=user_id,
            entry_type="system",
            category="strategy",
            title=f"Archived {count} implementation tasks for {strategy_name}",
            source_type="system",
            metadata={
                "strategy_id": str(strategy_id),
                "tax_year": tax_year,
                "task_count": count,
            },
        )

    return count


# ─── Profile flags ────────────────────────────────────────────────────────


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
