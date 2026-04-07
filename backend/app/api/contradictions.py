"""
Contradiction Detection API endpoints.

Routes:
  GET    /api/clients/{client_id}/contradictions                       — Paginated list
  GET    /api/clients/{client_id}/contradictions/{contradiction_id}    — Detail with source docs
  PATCH  /api/clients/{client_id}/contradictions/{contradiction_id}    — Resolve or dismiss
  POST   /api/clients/{client_id}/contradictions/scan                  — Trigger full scan
  GET    /api/contradictions/summary                                   — Cross-client dashboard summary
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.data_contradiction import DataContradiction
from app.models.document import Document
from app.schemas.contradiction import (
    ContradictionListResponse,
    ContradictionResponse,
    ContradictionScanResult,
)
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.contradiction_service import (
    dismiss_contradiction,
    resolve_contradiction,
    run_full_scan,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Severity sort order: high → medium → low
_SEVERITY_ORDER = case(
    (DataContradiction.severity == "high", 0),
    (DataContradiction.severity == "medium", 1),
    else_=2,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_client(db: Session, client_id: UUID, auth: AuthContext) -> None:
    check_client_access(auth, client_id, db)
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.org_id == auth.org_id)
        .first()
    )
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")


# ---------------------------------------------------------------------------
# Request / response schemas (endpoint-specific)
# ---------------------------------------------------------------------------


class ContradictionPatchRequest(BaseModel):
    status: str = Field(..., pattern=r"^(resolved|dismissed)$")
    resolution_note: Optional[str] = None


class ContradictionListWithMeta(ContradictionListResponse):
    open_count: int = 0
    page: int = 1
    per_page: int = 20


class ScanResponse(BaseModel):
    new_contradictions: int = 0
    existing_open: int = 0


class ContradictionDetailResponse(ContradictionResponse):
    source_a_document_name: Optional[str] = None
    source_b_document_name: Optional[str] = None


class ClientContradictionSummary(BaseModel):
    client_id: UUID
    client_name: str
    open_count: int
    high_count: int


class ContradictionDashboardSummary(BaseModel):
    clients: List[ClientContradictionSummary]
    total_open: int


# ---------------------------------------------------------------------------
# 1. List contradictions (paginated)
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/contradictions",
    response_model=ContradictionListWithMeta,
    summary="List contradictions for a client",
)
async def list_contradictions(
    client_id: UUID,
    status_filter: Optional[str] = Query(default="open", alias="status"),
    severity: Optional[str] = Query(default=None),
    tax_year: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ContradictionListWithMeta:
    _verify_client(db, client_id, auth)

    base_q = db.query(DataContradiction).filter(
        DataContradiction.client_id == client_id,
    )

    if status_filter:
        base_q = base_q.filter(DataContradiction.status == status_filter)
    if severity:
        base_q = base_q.filter(DataContradiction.severity == severity)
    if tax_year:
        base_q = base_q.filter(DataContradiction.tax_year == tax_year)

    total = base_q.count()

    rows = (
        base_q
        .order_by(_SEVERITY_ORDER, DataContradiction.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    open_count = (
        db.query(func.count(DataContradiction.id))
        .filter(
            DataContradiction.client_id == client_id,
            DataContradiction.status == "open",
        )
        .scalar()
    ) or 0

    return ContradictionListWithMeta(
        contradictions=[ContradictionResponse.model_validate(r) for r in rows],
        total=total,
        open_count=open_count,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# 2. Contradiction detail
# ---------------------------------------------------------------------------


@router.get(
    "/clients/{client_id}/contradictions/{contradiction_id}",
    response_model=ContradictionDetailResponse,
    summary="Get contradiction detail with source document names",
)
async def get_contradiction(
    client_id: UUID,
    contradiction_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ContradictionDetailResponse:
    _verify_client(db, client_id, auth)

    row = (
        db.query(DataContradiction)
        .filter(
            DataContradiction.id == contradiction_id,
            DataContradiction.client_id == client_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction not found"
        )

    # Look up source document filenames
    source_a_name = None
    source_b_name = None
    if row.source_a_id:
        doc = db.query(Document.filename).filter(Document.id == row.source_a_id).first()
        if doc:
            source_a_name = doc.filename
    if row.source_b_id:
        doc = db.query(Document.filename).filter(Document.id == row.source_b_id).first()
        if doc:
            source_b_name = doc.filename

    data = ContradictionResponse.model_validate(row).model_dump()
    data["source_a_document_name"] = source_a_name
    data["source_b_document_name"] = source_b_name
    return ContradictionDetailResponse(**data)


# ---------------------------------------------------------------------------
# 3. Update (resolve / dismiss)
# ---------------------------------------------------------------------------


@router.patch(
    "/clients/{client_id}/contradictions/{contradiction_id}",
    response_model=ContradictionResponse,
    summary="Resolve or dismiss a contradiction",
)
async def update_contradiction(
    client_id: UUID,
    contradiction_id: UUID,
    body: ContradictionPatchRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ContradictionResponse:
    _verify_client(db, client_id, auth)

    # Verify the contradiction belongs to this client
    row = (
        db.query(DataContradiction)
        .filter(
            DataContradiction.id == contradiction_id,
            DataContradiction.client_id == client_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction not found"
        )

    if body.status == "resolved":
        updated = resolve_contradiction(
            contradiction_id=contradiction_id,
            user_id=auth.user_id,
            resolution_note=body.resolution_note or "",
            db=db,
        )
    else:
        updated = dismiss_contradiction(
            contradiction_id=contradiction_id,
            user_id=auth.user_id,
            db=db,
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction not found"
        )

    return ContradictionResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# 4. Scan
# ---------------------------------------------------------------------------


@router.post(
    "/clients/{client_id}/contradictions/scan",
    response_model=ScanResponse,
    summary="Trigger a full contradiction scan for this client",
)
async def scan_contradictions(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ScanResponse:
    _verify_client(db, client_id, auth)

    result = run_full_scan(client_id, auth.user_id, db)

    return ScanResponse(
        new_contradictions=result["new_contradictions"],
        existing_open=result["total_open"],
    )


# ---------------------------------------------------------------------------
# 5. Cross-client dashboard summary
# ---------------------------------------------------------------------------


@router.get(
    "/contradictions/summary",
    response_model=ContradictionDashboardSummary,
    summary="Cross-client contradiction summary for the dashboard",
)
async def contradictions_summary(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ContradictionDashboardSummary:
    # Get all clients in this org
    client_rows = (
        db.query(Client.id, Client.name)
        .filter(Client.org_id == auth.org_id)
        .all()
    )
    if not client_rows:
        return ContradictionDashboardSummary(clients=[], total_open=0)

    client_ids = [r.id for r in client_rows]
    client_names = {r.id: r.name for r in client_rows}

    # Aggregate open contradictions per client with high-severity count
    rows = (
        db.query(
            DataContradiction.client_id,
            func.count(DataContradiction.id).label("open_count"),
            func.count(
                case((DataContradiction.severity == "high", 1))
            ).label("high_count"),
        )
        .filter(
            DataContradiction.client_id.in_(client_ids),
            DataContradiction.status == "open",
        )
        .group_by(DataContradiction.client_id)
        .all()
    )

    clients = []
    total_open = 0
    for cid, open_count, high_count in rows:
        total_open += open_count
        clients.append(
            ClientContradictionSummary(
                client_id=cid,
                client_name=client_names.get(cid, "Unknown"),
                open_count=open_count,
                high_count=high_count,
            )
        )

    # Sort: high_count DESC, then open_count DESC
    clients.sort(key=lambda c: (-c.high_count, -c.open_count))

    return ContradictionDashboardSummary(clients=clients, total_open=total_open)
