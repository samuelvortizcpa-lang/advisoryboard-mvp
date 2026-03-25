"""
Tax Strategy Matrix endpoints.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.tax_strategy import TaxStrategy
from app.schemas.strategy import (
    BulkStatusResponse,
    BulkStatusUpdate,
    ProfileFlagsResponse,
    ProfileFlagsUpdate,
    StrategyChecklistResponse,
    StrategyHistoryResponse,
    StrategyStatusUpdate,
    TaxStrategyResponse,
)
from app.services import strategy_service
from app.services.auth_context import AuthContext, check_client_access, get_auth

router = APIRouter()


# ─── Reference list ───────────────────────────────────────────────────────────


@router.get("/tax-strategies", response_model=list[TaxStrategyResponse])
async def list_strategies(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[TaxStrategyResponse]:
    """Return all active strategies from the reference table."""
    rows = (
        db.query(TaxStrategy)
        .filter(TaxStrategy.is_active == True)  # noqa: E712
        .order_by(TaxStrategy.category, TaxStrategy.display_order)
        .all()
    )
    return [TaxStrategyResponse.model_validate(r) for r in rows]


# ─── Client-specific checklist ────────────────────────────────────────────────


@router.get(
    "/clients/{client_id}/strategies",
    response_model=StrategyChecklistResponse,
)
async def get_client_strategies(
    client_id: UUID,
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> StrategyChecklistResponse:
    """Return strategies applicable to this client, with status for the given year."""
    check_client_access(auth, client_id, db)
    tax_year = year if year is not None else date.today().year
    result = strategy_service.get_strategies_for_client(db, client_id, tax_year)
    return StrategyChecklistResponse(**result)


# ─── Bulk status update (must be before {strategy_id} to avoid path conflict) ─


@router.put(
    "/clients/{client_id}/strategies/bulk",
    response_model=BulkStatusResponse,
)
async def bulk_update(
    client_id: UUID,
    body: BulkStatusUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> BulkStatusResponse:
    """Bulk upsert strategy statuses for a client."""
    check_client_access(auth, client_id, db)
    updates = [
        {
            "strategy_id": item.strategy_id,
            "tax_year": item.tax_year,
            "status": item.status,
            "notes": item.notes,
            "estimated_impact": item.estimated_impact,
        }
        for item in body.updates
    ]
    count = strategy_service.bulk_update_statuses(db, client_id, updates, user_id=auth.user_id)
    return BulkStatusResponse(updated=count)


# ─── History / comparison (must be before {strategy_id} to avoid path conflict)


@router.get(
    "/clients/{client_id}/strategies/history",
    response_model=StrategyHistoryResponse,
)
async def get_history(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> StrategyHistoryResponse:
    """Return year-over-year strategy comparison data."""
    check_client_access(auth, client_id, db)
    result = strategy_service.get_strategy_history(db, client_id)
    return StrategyHistoryResponse(**result)


# ─── Single status update ────────────────────────────────────────────────────


@router.put("/clients/{client_id}/strategies/{strategy_id}")
async def update_status(
    client_id: UUID,
    strategy_id: UUID,
    body: StrategyStatusUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
):
    """Upsert the status of a single strategy for this client + year."""
    check_client_access(auth, client_id, db)
    row = strategy_service.update_strategy_status(
        db,
        client_id=client_id,
        strategy_id=strategy_id,
        tax_year=body.tax_year,
        new_status=body.status,
        notes=body.notes,
        estimated_impact=body.estimated_impact,
        user_id=auth.user_id,
    )
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "strategy_id": str(row.strategy_id),
        "tax_year": row.tax_year,
        "status": row.status,
        "notes": row.notes,
        "estimated_impact": float(row.estimated_impact) if row.estimated_impact is not None else None,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ─── Profile flags ────────────────────────────────────────────────────────────


@router.patch(
    "/clients/{client_id}/profile-flags",
    response_model=ProfileFlagsResponse,
)
async def update_flags(
    client_id: UUID,
    body: ProfileFlagsUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ProfileFlagsResponse:
    """Partial update of the client's tax strategy profile flags."""
    check_client_access(auth, client_id, db)
    flags_dict = body.model_dump(exclude_unset=True)
    client = strategy_service.update_profile_flags(db, client_id, flags_dict)
    return ProfileFlagsResponse.model_validate(client)
