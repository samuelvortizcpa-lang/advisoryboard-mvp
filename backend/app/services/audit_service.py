"""
Audit logging service.

Fire-and-forget: logging failures never break the request.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.services.auth_context import AuthContext

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    auth: AuthContext,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Record an audit log entry. Silently swallows errors."""
    try:
        ip_address = None
        user_agent = None
        if request is not None:
            ip_address = request.client.host if request.client else None
            user_agent = (request.headers.get("user-agent") or "")[:512]

        entry = AuditLog(
            user_id=auth.user_id,
            org_id=auth.org_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            detail=detail,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        db.commit()
    except Exception:
        logger.warning("Failed to write audit log for %s", action, exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass


def get_audit_logs(
    db: Session,
    org_id: UUID,
    filters: dict[str, Any] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """Query audit logs for an organization with optional filters."""
    query = db.query(AuditLog).filter(AuditLog.org_id == org_id)

    if filters:
        if filters.get("user_id"):
            query = query.filter(AuditLog.user_id == filters["user_id"])
        if filters.get("action"):
            query = query.filter(AuditLog.action == filters["action"])
        if filters.get("resource_type"):
            query = query.filter(AuditLog.resource_type == filters["resource_type"])
        if filters.get("resource_id"):
            query = query.filter(AuditLog.resource_id == filters["resource_id"])
        if filters.get("date_from"):
            query = query.filter(AuditLog.timestamp >= filters["date_from"])
        if filters.get("date_to"):
            query = query.filter(AuditLog.timestamp <= filters["date_to"])

    total = query.count()
    logs = (
        query
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return logs, total
