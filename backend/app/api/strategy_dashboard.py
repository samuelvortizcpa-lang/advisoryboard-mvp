"""
Cross-client strategy dashboard endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.strategy import (
    ClientStrategySummary,
    StrategyAdoption,
    StrategyOverview,
    UnreviewedAlert,
)
from app.services import strategy_dashboard_service
from app.services.auth_context import AuthContext, get_auth

router = APIRouter()


@router.get("/strategy-dashboard/overview", response_model=StrategyOverview)
async def overview(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> StrategyOverview:
    """Aggregate strategy stats across all accessible clients."""
    result = strategy_dashboard_service.get_strategy_overview(
        db,
        user_id=auth.user_id,
        org_id=auth.org_id,
        org_role=auth.org_role,
        tax_year=year,
    )
    return StrategyOverview(**result)


@router.get(
    "/strategy-dashboard/clients",
    response_model=list[ClientStrategySummary],
)
async def client_summaries(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[ClientStrategySummary]:
    """Per-client strategy coverage, sorted by least coverage first."""
    rows = strategy_dashboard_service.get_client_strategy_summary(
        db,
        user_id=auth.user_id,
        org_id=auth.org_id,
        org_role=auth.org_role,
        tax_year=year,
    )
    return [ClientStrategySummary(**r) for r in rows]


@router.get(
    "/strategy-dashboard/adoption",
    response_model=list[StrategyAdoption],
)
async def adoption(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[StrategyAdoption]:
    """Per-strategy adoption rates across all accessible clients."""
    rows = strategy_dashboard_service.get_strategy_adoption(
        db,
        user_id=auth.user_id,
        org_id=auth.org_id,
        org_role=auth.org_role,
        tax_year=year,
    )
    return [StrategyAdoption(**r) for r in rows]


@router.get(
    "/strategy-dashboard/alerts",
    response_model=list[UnreviewedAlert],
)
async def alerts(
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> list[UnreviewedAlert]:
    """Top unreviewed client+strategy combinations needing attention."""
    rows = strategy_dashboard_service.get_unreviewed_alerts(
        db,
        user_id=auth.user_id,
        org_id=auth.org_id,
        org_role=auth.org_role,
        tax_year=year,
    )
    return [UnreviewedAlert(**r) for r in rows]
