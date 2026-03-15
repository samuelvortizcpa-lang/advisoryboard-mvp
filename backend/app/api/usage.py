"""
Token usage API endpoints.

Routes (all require Clerk JWT auth):
  GET  /api/usage/summary?days=30
  GET  /api/usage/clients/{client_id}?days=30
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.services import user_service
from app.services.token_tracking_service import get_usage_by_client, get_usage_summary

router = APIRouter()


@router.get(
    "/usage/summary",
    summary="Get AI token usage summary for the authenticated user",
)
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> dict:
    user = user_service.get_or_create_user(db, current_user)
    return get_usage_summary(db, user_id=user.clerk_id, days=days)


@router.get(
    "/usage/clients/{client_id}",
    summary="Get AI token usage for a specific client",
)
async def usage_by_client(
    client_id: UUID,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> dict:
    user = user_service.get_or_create_user(db, current_user)
    return get_usage_by_client(db, user_id=user.clerk_id, client_id=client_id, days=days)
