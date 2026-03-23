"""
Client assignment endpoints — assign org members to clients.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.client_assignment import ClientAssignment
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.services.auth_context import AuthContext, get_auth, require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────


class AssignmentResponse(BaseModel):
    id: str
    client_id: str
    client_name: Optional[str] = None
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    org_id: str
    assigned_by: str
    assigned_at: str
    role: str


class CreateAssignmentRequest(BaseModel):
    user_id: str


class AssignedClientInfo(BaseModel):
    client_id: str
    client_name: str


class MemberAssignments(BaseModel):
    user_id: str
    user_name: str
    user_email: str
    assigned_clients: List[AssignedClientInfo]


class MyClientResponse(BaseModel):
    id: str
    name: str
    document_count: int
    action_item_count: int


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_org_client(db: Session, client_id: UUID, org_id: UUID) -> Client:
    """Fetch a client and verify it belongs to the given org."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client or client.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return client


def _verify_org_member(db: Session, user_id: str, org_id: UUID) -> None:
    """Verify the user_id is an active member of the org."""
    member = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not an active member of this organization",
        )


def _user_info(db: Session, user_id: str) -> tuple[str, str]:
    """Look up name and email from the local users table."""
    usr = db.query(User).filter(User.clerk_id == user_id).first()
    if not usr:
        return user_id, ""
    parts = [usr.first_name, usr.last_name]
    name = " ".join(p for p in parts if p) or user_id
    return name, usr.email or ""


def _assignment_to_response(
    assignment: ClientAssignment,
    db: Session,
    client_name: Optional[str] = None,
) -> AssignmentResponse:
    """Convert a ClientAssignment ORM object to a response dict."""
    name, email = _user_info(db, assignment.user_id)
    if client_name is None:
        client = db.query(Client).filter(Client.id == assignment.client_id).first()
        client_name = client.name if client else ""
    return AssignmentResponse(
        id=str(assignment.id),
        client_id=str(assignment.client_id),
        client_name=client_name,
        user_id=assignment.user_id,
        user_name=name,
        user_email=email,
        org_id=str(assignment.org_id),
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at.isoformat(),
        role=assignment.role,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/clients/{client_id}/assignments",
    response_model=List[AssignmentResponse],
    summary="List members assigned to a client",
)
async def list_client_assignments(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[AssignmentResponse]:
    client = _get_org_client(db, client_id, auth.org_id)

    rows = (
        db.query(ClientAssignment)
        .filter(ClientAssignment.client_id == client_id)
        .order_by(ClientAssignment.assigned_at)
        .all()
    )

    return [_assignment_to_response(r, db, client.name) for r in rows]


@router.post(
    "/clients/{client_id}/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a member to a client",
)
async def create_assignment(
    client_id: UUID,
    body: CreateAssignmentRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> AssignmentResponse:
    require_admin(auth)
    client = _get_org_client(db, client_id, auth.org_id)
    _verify_org_member(db, body.user_id, auth.org_id)

    # Check for duplicate
    existing = (
        db.query(ClientAssignment)
        .filter(
            ClientAssignment.client_id == client_id,
            ClientAssignment.user_id == body.user_id,
            ClientAssignment.org_id == auth.org_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already assigned to this client",
        )

    assignment = ClientAssignment(
        client_id=client_id,
        user_id=body.user_id,
        org_id=auth.org_id,
        assigned_by=auth.user_id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    return _assignment_to_response(assignment, db, client.name)


@router.delete(
    "/clients/{client_id}/assignments/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove a member's assignment from a client",
)
async def delete_assignment(
    client_id: UUID,
    user_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    require_admin(auth)
    _get_org_client(db, client_id, auth.org_id)

    row = (
        db.query(ClientAssignment)
        .filter(
            ClientAssignment.client_id == client_id,
            ClientAssignment.user_id == user_id,
            ClientAssignment.org_id == auth.org_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    db.delete(row)
    db.commit()


@router.get(
    "/organizations/{org_id}/assignments",
    response_model=List[MemberAssignments],
    summary="All client assignments across the org, grouped by member",
)
async def list_org_assignments(
    org_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[MemberAssignments]:
    if auth.org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    require_admin(auth)

    rows = (
        db.query(ClientAssignment, Client.name)
        .join(Client, ClientAssignment.client_id == Client.id)
        .filter(ClientAssignment.org_id == org_id)
        .order_by(ClientAssignment.user_id, Client.name)
        .all()
    )

    # Group by member
    grouped: dict[str, list[AssignedClientInfo]] = {}
    for assignment, client_name in rows:
        grouped.setdefault(assignment.user_id, []).append(
            AssignedClientInfo(
                client_id=str(assignment.client_id),
                client_name=client_name or "",
            )
        )

    result: list[MemberAssignments] = []
    for uid, clients in grouped.items():
        name, email = _user_info(db, uid)
        result.append(
            MemberAssignments(
                user_id=uid,
                user_name=name,
                user_email=email,
                assigned_clients=clients,
            )
        )

    return result


@router.get(
    "/users/me/clients",
    response_model=List[MyClientResponse],
    summary="Clients assigned to the current user",
)
async def list_my_clients(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[MyClientResponse]:
    from app.models.action_item import ActionItem
    from app.models.document import Document

    # Check if org has any assignments at all
    org_has_assignments = (
        db.query(func.count(ClientAssignment.id))
        .filter(ClientAssignment.org_id == auth.org_id)
        .scalar()
        or 0
    ) > 0

    if org_has_assignments:
        # Return only clients assigned to this user
        assigned_client_ids = (
            db.query(ClientAssignment.client_id)
            .filter(
                ClientAssignment.user_id == auth.user_id,
                ClientAssignment.org_id == auth.org_id,
            )
            .subquery()
        )
        clients = (
            db.query(Client)
            .filter(Client.id.in_(assigned_client_ids))
            .order_by(Client.name)
            .all()
        )
    else:
        # Backward compat: no assignments exist yet, return all org clients
        clients = (
            db.query(Client)
            .filter(Client.org_id == auth.org_id)
            .order_by(Client.name)
            .all()
        )

    result: list[MyClientResponse] = []
    for c in clients:
        doc_count = (
            db.query(func.count(Document.id))
            .filter(Document.client_id == c.id)
            .scalar()
        ) or 0
        ai_count = (
            db.query(func.count(ActionItem.id))
            .filter(ActionItem.client_id == c.id)
            .scalar()
        ) or 0
        result.append(
            MyClientResponse(
                id=str(c.id),
                name=c.name,
                document_count=doc_count,
                action_item_count=ai_count,
            )
        )

    return result
