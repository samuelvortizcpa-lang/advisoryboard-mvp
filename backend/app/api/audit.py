"""
Audit log API endpoint.

Routes (all require org admin auth):
  GET /api/organizations/{org_id}/audit-log
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.audit_service import get_audit_logs
from app.services.auth_context import AuthContext, get_auth, require_admin

router = APIRouter()


class AuditLogEntry(BaseModel):
    id: str
    timestamp: str
    user_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    detail: Optional[dict[str, Any]] = None


class AuditLogResponse(BaseModel):
    logs: List[AuditLogEntry]
    total: int
    limit: int
    offset: int


@router.get(
    "/organizations/{org_id}/audit-log",
    response_model=AuditLogResponse,
    summary="List audit logs for the organization",
)
async def list_audit_logs(
    org_id: UUID,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    user_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> AuditLogResponse:
    require_admin(auth)

    filters = {}
    if action:
        filters["action"] = action
    if resource_type:
        filters["resource_type"] = resource_type
    if user_id:
        filters["user_id"] = user_id
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    logs, total = get_audit_logs(
        db, org_id=org_id, filters=filters or None, limit=limit, offset=offset,
    )

    return AuditLogResponse(
        logs=[
            AuditLogEntry(
                id=str(log.id),
                timestamp=log.timestamp.isoformat(),
                user_id=log.user_id,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                detail=log.detail,
            )
            for log in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
