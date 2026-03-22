"""
Dashboard stats endpoint — aggregate counts for the current user's organization.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.action_item import ActionItem
from app.models.client import Client
from app.models.document import Document
from app.services.auth_context import AuthContext, get_auth

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
    auth: AuthContext = Depends(get_auth),
) -> DashboardStatsResponse:
    client_count = (
        db.query(Client)
        .filter(Client.org_id == auth.org_id)
        .count()
    )

    # Documents across all of the org's clients
    document_count = (
        db.query(Document)
        .join(Client, Document.client_id == Client.id)
        .filter(Client.org_id == auth.org_id)
        .count()
    )

    # Interactions = action items across all of the org's clients
    interaction_count = (
        db.query(ActionItem)
        .join(Client, ActionItem.client_id == Client.id)
        .filter(Client.org_id == auth.org_id)
        .count()
    )

    return DashboardStatsResponse(
        clients=client_count,
        documents=document_count,
        interactions=interaction_count,
    )
