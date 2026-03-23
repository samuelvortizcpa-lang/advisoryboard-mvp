"""
Org-aware authentication context for all API endpoints.

Replaces the old pattern of extracting user_id and filtering by owner_id.
Every endpoint should depend on `get_auth` to get an AuthContext, then use
auth.org_id to scope queries.

Usage:
    from app.services.auth_context import AuthContext, get_auth, check_client_access

    @router.get("/clients")
    async def list_clients(auth: AuthContext = Depends(get_auth)):
        # auth.user_id, auth.org_id, auth.org_role are all available
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.client import Client
from app.models.client_access import ClientAccess
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.services import organization_service, user_service

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    user_id: str          # Clerk user ID (always present)
    org_id: UUID          # Active organization ID
    org_role: str         # User's role in the org ('admin', 'member', 'readonly')
    is_personal_org: bool  # True if this is a solo/personal workspace


async def get_auth_context(
    request: Request,
    db: Session,
    current_user: dict,
) -> AuthContext:
    """
    Resolve the full auth context for the current request.

    1. Extract user_id from the already-verified Clerk JWT payload.
    2. Determine org: X-Org-Id header > auto-resolve > auto-create personal.
    3. Verify the user is an active member of the resolved org.
    4. Return a populated AuthContext.
    """
    user_id: str = current_user["user_id"]

    # Ensure the local User row exists (mirrors Clerk user)
    user_service.get_or_create_user(db, current_user)

    # --- Resolve organization ---
    org_id_header = request.headers.get("X-Org-Id")

    if org_id_header:
        # Explicit org selection via header
        try:
            org_id = UUID(org_id_header)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid X-Org-Id header",
            )

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization not found",
            )
    else:
        # Auto-resolve: pick the user's active org
        org = organization_service.get_active_org_for_user(user_id, db)

        if org is None:
            # First-time user — auto-create a personal workspace
            user_email = current_user.get("email") or f"{user_id}@unknown"
            parts = [current_user.get("first_name"), current_user.get("last_name")]
            user_name = " ".join(p for p in parts if p) or None

            org = organization_service.get_or_create_personal_org(
                user_id=user_id,
                user_email=user_email,
                user_name=user_name,
                db=db,
            )

    # --- Verify membership ---
    member = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org.id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    return AuthContext(
        user_id=user_id,
        org_id=org.id,
        org_role=member.role,
        is_personal_org=org.org_type == "personal",
    )


# ---------------------------------------------------------------------------
# Client access check
# ---------------------------------------------------------------------------

def check_client_access(
    auth: AuthContext,
    client_id: UUID,
    db: Session,
) -> bool:
    """
    Verify the authenticated user can access the given client.

    Rules:
      1. The client must belong to the user's active org.
      2. Admins always have access to any client in their org.
      3. Assignment-based access (opt-in): if the org has any client
         assignments, non-admin members can only access assigned clients.
      4. If no assignments exist, fall back to client_access records:
         - No client_access records → open access (default allow).
         - client_access records exist → user must have access_level != 'none'.

    Raises HTTPException 403 if access is denied.
    Returns True otherwise.
    """
    from app.services.assignment_service import get_accessible_client_ids

    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.org_id == auth.org_id)
        .first()
    )
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this client",
        )

    # Admins see everything in their org
    if auth.org_role == "admin":
        return True

    # Assignment-based access: if the org has assignments, check them first
    accessible_ids = get_accessible_client_ids(
        auth.user_id, auth.org_id, False, db
    )
    if accessible_ids is not None:
        # Org uses assignments — only allow assigned clients
        if client_id not in accessible_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this client",
            )
        return True

    # No assignments in org — fall back to client_access records
    has_any_access_records = (
        db.query(ClientAccess.id)
        .filter(ClientAccess.client_id == client_id)
        .first()
    ) is not None

    if not has_any_access_records:
        # No access records means open access within the org
        return True

    # Access records exist — check this specific user
    user_access = (
        db.query(ClientAccess)
        .filter(
            ClientAccess.client_id == client_id,
            ClientAccess.user_id == auth.user_id,
        )
        .first()
    )
    if user_access is None or user_access.access_level == "none":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this client",
        )

    return True


# ---------------------------------------------------------------------------
# Admin guard
# ---------------------------------------------------------------------------

def require_admin(auth: AuthContext) -> None:
    """Raise 403 if the user is not an org admin."""
    if auth.org_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_auth(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AuthContext:
    """
    FastAPI dependency that every org-aware endpoint should use.

    Usage:
        @router.get("/something")
        async def handler(auth: AuthContext = Depends(get_auth)):
            # auth.user_id, auth.org_id, auth.org_role
            ...
    """
    return await get_auth_context(request, db, current_user)
