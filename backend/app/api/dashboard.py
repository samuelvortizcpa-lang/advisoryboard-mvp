"""
Dashboard stats endpoint — aggregate counts for the current user.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.document import Document
from app.services import user_service

router = APIRouter()


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
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> DashboardStatsResponse:
    user = user_service.get_or_create_user(db, current_user)

    client_count = (
        db.query(Client)
        .filter(Client.owner_id == user.id)
        .count()
    )

    # Documents across all of the user's clients
    document_count = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(Client.owner_id == user.id)
        .count()
    )

    # Interactions = action items across all of the user's clients
    interaction_count = (
        db.query(ActionItem)
        .join(Client, ActionItem.client_id == Client.id)
        .filter(Client.owner_id == user.id)
        .count()
    )

    return DashboardStatsResponse(
        clients=client_count,
        documents=document_count,
        interactions=interaction_count,
    )
