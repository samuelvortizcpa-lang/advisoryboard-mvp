"""
Organization management API endpoints.

Routes:
  GET    /api/organizations                                         — list user's orgs
  POST   /api/organizations                                         — create firm org
  GET    /api/organizations/{org_id}                                 — org details
  PATCH  /api/organizations/{org_id}                                 — update org

  GET    /api/organizations/{org_id}/members                         — list members
  POST   /api/organizations/{org_id}/members                         — invite/add member
  PATCH  /api/organizations/{org_id}/members/{user_id}               — update role
  DELETE /api/organizations/{org_id}/members/{user_id}               — remove member

  GET    /api/organizations/{org_id}/clients/{client_id}/access      — list access
  POST   /api/organizations/{org_id}/clients/{client_id}/access      — grant access
  DELETE /api/organizations/{org_id}/clients/{client_id}/access/{user_id} — revoke
  POST   /api/organizations/{org_id}/clients/{client_id}/access/restrict — lock down
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.client import Client
from app.models.client_access import ClientAccess
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User
from app.models.user_subscription import UserSubscription
from app.schemas.organization import (
    AddMemberRequest,
    OrgCreateRequest,
    OrgMemberResponse,
    OrgResponse,
)
from app.services import organization_service
from app.services.audit_service import log_action
from app.services.auth_context import AuthContext, get_auth, require_admin
from app.services.subscription_service import TIER_DEFAULTS, check_seat_limit, get_or_create_subscription

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response / request schemas (local to this file)
# ---------------------------------------------------------------------------


class OrgDetailResponse(OrgResponse):
    owner_user_id: str
    settings: dict = {}
    subscription_tier: Optional[str] = None
    client_count: int = 0
    created_at: datetime
    updated_at: datetime


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    settings: Optional[dict] = None


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., max_length=50)


class ClientAccessResponse(BaseModel):
    id: UUID
    client_id: UUID
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    access_level: str
    assigned_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GrantAccessRequest(BaseModel):
    user_id: str = Field(..., max_length=255)
    access_level: str = Field(default="full", max_length=50)


class ClientAccessSummary(BaseModel):
    mode: str  # "open" or "restricted"
    records: List[ClientAccessResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_membership(
    auth: AuthContext, org_id: UUID, db: Session,
) -> OrganizationMember:
    """Return the user's active membership in this org, or raise 403."""
    member = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == auth.user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )
    return member


def _require_org_admin(
    auth: AuthContext, org_id: UUID, db: Session,
) -> OrganizationMember:
    """Return the user's active admin membership, or raise 403."""
    member = _require_membership(auth, org_id, db)
    if member.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return member


def _require_org_client(org_id: UUID, client_id: UUID, db: Session) -> Client:
    """Verify the client belongs to this org, or raise 404."""
    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.org_id == org_id)
        .first()
    )
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found in this organization",
        )
    return client


# ---------------------------------------------------------------------------
# 1. GET /organizations — list user's orgs
# ---------------------------------------------------------------------------


@router.get(
    "/organizations",
    response_model=List[OrgResponse],
    summary="List organizations the current user belongs to",
)
async def list_organizations(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[OrgResponse]:
    orgs = organization_service.get_user_orgs(auth.user_id, db)

    results = []
    for o in orgs:
        # Fetch subscription tier for this org
        sub = (
            db.query(UserSubscription)
            .filter(UserSubscription.org_id == o["id"])
            .first()
        )
        resp = OrgResponse(
            id=o["id"],
            name=o["name"],
            slug=o["slug"],
            org_type=o["org_type"],
            max_members=o["max_members"],
            member_count=o["member_count"],
            role=o["role"],
        )
        results.append(resp)

    return results


# ---------------------------------------------------------------------------
# 2. POST /organizations — create firm org
# ---------------------------------------------------------------------------


@router.post(
    "/organizations",
    response_model=OrgDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new firm organization",
)
async def create_organization(
    body: OrgCreateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> OrgDetailResponse:
    # Check subscription tier — must be professional or firm
    sub = get_or_create_subscription(db, auth.user_id, org_id=auth.org_id)
    if sub.tier not in ("professional", "firm"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upgrade to Professional or Firm tier to create an organization.",
        )

    if not body.name or not body.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization name is required.",
        )

    tier_config = TIER_DEFAULTS.get(sub.tier, TIER_DEFAULTS["free"])
    max_members = tier_config["max_members"]

    org = organization_service.create_firm_org(
        name=body.name.strip(),
        slug=body.slug,
        owner_user_id=auth.user_id,
        clerk_org_id=None,
        max_members=max_members,
        db=db,
    )

    client_count = (
        db.query(Client).filter(Client.org_id == org.id).count()
    )

    return OrgDetailResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        org_type=org.org_type,
        max_members=org.max_members,
        member_count=1,
        role="admin",
        owner_user_id=org.owner_user_id,
        settings=org.settings or {},
        subscription_tier=sub.tier,
        client_count=client_count,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# ---------------------------------------------------------------------------
# 3. GET /organizations/{org_id} — org details
# ---------------------------------------------------------------------------


@router.get(
    "/organizations/{org_id}",
    response_model=OrgDetailResponse,
    summary="Get organization details",
)
async def get_organization(
    org_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> OrgDetailResponse:
    member = _require_membership(auth, org_id, db)

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    member_count = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.is_active.is_(True),
        )
        .count()
    )

    client_count = (
        db.query(Client).filter(Client.org_id == org_id).count()
    )

    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.org_id == org_id)
        .first()
    )

    return OrgDetailResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        org_type=org.org_type,
        max_members=org.max_members,
        member_count=member_count,
        role=member.role,
        owner_user_id=org.owner_user_id,
        settings=org.settings or {},
        subscription_tier=sub.tier if sub else None,
        client_count=client_count,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# ---------------------------------------------------------------------------
# 4. PATCH /organizations/{org_id} — update org
# ---------------------------------------------------------------------------


@router.patch(
    "/organizations/{org_id}",
    response_model=OrgDetailResponse,
    summary="Update organization name or settings",
)
async def update_organization(
    org_id: UUID,
    body: OrgUpdateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> OrgDetailResponse:
    _require_org_admin(auth, org_id, db)

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Organization name cannot be empty.",
            )
        org.name = body.name.strip()

    if body.settings is not None:
        org.settings = body.settings

    db.commit()
    db.refresh(org)

    member_count = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.is_active.is_(True),
        )
        .count()
    )
    client_count = (
        db.query(Client).filter(Client.org_id == org_id).count()
    )
    sub = (
        db.query(UserSubscription)
        .filter(UserSubscription.org_id == org_id)
        .first()
    )

    return OrgDetailResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        org_type=org.org_type,
        max_members=org.max_members,
        member_count=member_count,
        role="admin",
        owner_user_id=org.owner_user_id,
        settings=org.settings or {},
        subscription_tier=sub.tier if sub else None,
        client_count=client_count,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# ---------------------------------------------------------------------------
# 5. GET /organizations/{org_id}/members — list members
# ---------------------------------------------------------------------------


@router.get(
    "/organizations/{org_id}/members",
    response_model=List[OrgMemberResponse],
    summary="List organization members",
)
async def list_members(
    org_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> List[OrgMemberResponse]:
    _require_membership(auth, org_id, db)

    members = organization_service.get_org_members(str(org_id), auth.user_id, db)
    if members is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )

    return [OrgMemberResponse(**m) for m in members]


# ---------------------------------------------------------------------------
# 6. POST /organizations/{org_id}/members — invite/add member
# ---------------------------------------------------------------------------


@router.post(
    "/organizations/{org_id}/members",
    response_model=OrgMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member to the organization",
)
async def add_member(
    org_id: UUID,
    body: AddMemberRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> OrgMemberResponse:
    _require_org_admin(auth, org_id, db)

    if body.role not in ("admin", "member", "readonly"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin', 'member', or 'readonly'.",
        )

    # Enforce seat limit before adding
    seat_check = check_seat_limit(org_id, db)
    if not seat_check["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": "Seat limit reached. Purchase additional seats to invite more members.",
                "seat_info": {
                    "current": seat_check["current"],
                    "limit": seat_check["limit"],
                },
            },
        )

    # Look up user by email
    target_user = (
        db.query(User).filter(User.email == body.user_email).first()
    )
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user found with email '{body.user_email}'. They must sign up first.",
        )

    result = organization_service.add_member(
        org_id=str(org_id),
        user_id=target_user.clerk_id,
        role=body.role,
        invited_by=auth.user_id,
        db=db,
    )

    if isinstance(result, str):
        error_map = {
            "org_not_found": (status.HTTP_404_NOT_FOUND, "Organization not found"),
            "max_members_reached": (
                status.HTTP_403_FORBIDDEN,
                "Seat limit reached. Upgrade your plan to add more members.",
            ),
            "already_member": (
                status.HTTP_409_CONFLICT,
                "This user is already a member of the organization.",
            ),
        }
        code, detail = error_map.get(result, (status.HTTP_400_BAD_REQUEST, result))
        raise HTTPException(status_code=code, detail=detail)

    log_action(db, auth, "member.invite", "member", target_user.clerk_id,
               detail={"email": body.user_email, "role": body.role}, request=request)
    return OrgMemberResponse(
        id=result.id,
        user_id=result.user_id,
        user_email=target_user.email,
        user_name=(
            " ".join(p for p in (target_user.first_name, target_user.last_name) if p)
            or None
        ),
        role=result.role,
        joined_at=result.joined_at,
        is_active=result.is_active,
    )


# ---------------------------------------------------------------------------
# 7. PATCH /organizations/{org_id}/members/{user_id} — update role
# ---------------------------------------------------------------------------


@router.patch(
    "/organizations/{org_id}/members/{user_id}",
    response_model=OrgMemberResponse,
    summary="Update a member's role",
)
async def update_member_role(
    org_id: UUID,
    user_id: str,
    body: UpdateRoleRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> OrgMemberResponse:
    if body.role not in ("admin", "member", "readonly"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin', 'member', or 'readonly'.",
        )

    result = organization_service.update_member_role(
        org_id=str(org_id),
        target_user_id=user_id,
        new_role=body.role,
        requesting_user_id=auth.user_id,
        db=db,
    )

    if isinstance(result, str):
        error_map = {
            "not_admin": (status.HTTP_403_FORBIDDEN, "Admin access required"),
            "cannot_demote_owner": (
                status.HTTP_400_BAD_REQUEST,
                "Cannot change the organization owner's role.",
            ),
            "member_not_found": (status.HTTP_404_NOT_FOUND, "Member not found"),
        }
        code, detail = error_map.get(result, (status.HTTP_400_BAD_REQUEST, result))
        raise HTTPException(status_code=code, detail=detail)

    # Resolve user info for response
    user = db.query(User).filter(User.clerk_id == user_id).first()
    return OrgMemberResponse(
        id=result.id,
        user_id=result.user_id,
        user_email=user.email if user else None,
        user_name=(
            " ".join(p for p in (user.first_name, user.last_name) if p)
            if user else None
        ),
        role=result.role,
        joined_at=result.joined_at,
        is_active=result.is_active,
    )


# ---------------------------------------------------------------------------
# 8. DELETE /organizations/{org_id}/members/{user_id} — remove member
# ---------------------------------------------------------------------------


@router.delete(
    "/organizations/{org_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Remove a member from the organization",
)
async def remove_member(
    org_id: UUID,
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    result = organization_service.remove_member(
        org_id=str(org_id),
        target_user_id=user_id,
        requesting_user_id=auth.user_id,
        db=db,
    )

    if isinstance(result, str):
        error_map = {
            "not_admin": (status.HTTP_403_FORBIDDEN, "Admin access required"),
            "cannot_remove_owner": (
                status.HTTP_400_BAD_REQUEST,
                "Cannot remove the organization owner.",
            ),
            "member_not_found": (status.HTTP_404_NOT_FOUND, "Member not found"),
        }
        code, detail = error_map.get(result, (status.HTTP_400_BAD_REQUEST, result))
        raise HTTPException(status_code=code, detail=detail)

    log_action(db, auth, "member.remove", "member", user_id, request=request)


# ---------------------------------------------------------------------------
# 9. GET /organizations/{org_id}/clients/{client_id}/access — list access
# ---------------------------------------------------------------------------


@router.get(
    "/organizations/{org_id}/clients/{client_id}/access",
    response_model=ClientAccessSummary,
    summary="List who has access to a client",
)
async def list_client_access(
    org_id: UUID,
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientAccessSummary:
    member = _require_membership(auth, org_id, db)
    _require_org_client(org_id, client_id, db)

    # Non-admins need client access to view this
    if member.role != "admin":
        own_access = (
            db.query(ClientAccess)
            .filter(
                ClientAccess.client_id == client_id,
                ClientAccess.user_id == auth.user_id,
            )
            .first()
        )
        has_any = (
            db.query(ClientAccess.id)
            .filter(ClientAccess.client_id == client_id)
            .first()
        )
        if has_any and (own_access is None or own_access.access_level == "none"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this client",
            )

    records = (
        db.query(ClientAccess)
        .filter(ClientAccess.client_id == client_id)
        .all()
    )

    if not records:
        return ClientAccessSummary(mode="open", records=[])

    # Enrich with user info
    enriched = []
    for rec in records:
        user = db.query(User).filter(User.clerk_id == rec.user_id).first()
        enriched.append(
            ClientAccessResponse(
                id=rec.id,
                client_id=rec.client_id,
                user_id=rec.user_id,
                user_email=user.email if user else None,
                user_name=(
                    " ".join(p for p in (user.first_name, user.last_name) if p)
                    if user else None
                ),
                access_level=rec.access_level,
                assigned_by=rec.assigned_by,
                created_at=rec.created_at,
            )
        )

    return ClientAccessSummary(mode="restricted", records=enriched)


# ---------------------------------------------------------------------------
# 10. POST /organizations/{org_id}/clients/{client_id}/access — grant access
# ---------------------------------------------------------------------------


@router.post(
    "/organizations/{org_id}/clients/{client_id}/access",
    response_model=ClientAccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a member access to a client",
)
async def grant_client_access(
    org_id: UUID,
    client_id: UUID,
    body: GrantAccessRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientAccessResponse:
    _require_org_admin(auth, org_id, db)
    _require_org_client(org_id, client_id, db)

    if body.access_level not in ("full", "readonly", "none"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="access_level must be 'full', 'readonly', or 'none'.",
        )

    # Verify target user is an active member of the org
    target_member = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == body.user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if target_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not an active member of this organization.",
        )

    # Upsert
    existing = (
        db.query(ClientAccess)
        .filter(
            ClientAccess.client_id == client_id,
            ClientAccess.user_id == body.user_id,
        )
        .first()
    )
    if existing:
        existing.access_level = body.access_level
        existing.assigned_by = auth.user_id
        db.commit()
        db.refresh(existing)
        rec = existing
    else:
        rec = ClientAccess(
            client_id=client_id,
            user_id=body.user_id,
            access_level=body.access_level,
            assigned_by=auth.user_id,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

    user = db.query(User).filter(User.clerk_id == body.user_id).first()
    return ClientAccessResponse(
        id=rec.id,
        client_id=rec.client_id,
        user_id=rec.user_id,
        user_email=user.email if user else None,
        user_name=(
            " ".join(p for p in (user.first_name, user.last_name) if p)
            if user else None
        ),
        access_level=rec.access_level,
        assigned_by=rec.assigned_by,
        created_at=rec.created_at,
    )


# ---------------------------------------------------------------------------
# 11. DELETE /organizations/{org_id}/clients/{client_id}/access/{user_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/organizations/{org_id}/clients/{client_id}/access/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Revoke a member's access to a client",
)
async def revoke_client_access(
    org_id: UUID,
    client_id: UUID,
    user_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    _require_org_admin(auth, org_id, db)
    _require_org_client(org_id, client_id, db)

    record = (
        db.query(ClientAccess)
        .filter(
            ClientAccess.client_id == client_id,
            ClientAccess.user_id == user_id,
        )
        .first()
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access record not found.",
        )

    db.delete(record)
    db.commit()


# ---------------------------------------------------------------------------
# 12. POST /organizations/{org_id}/clients/{client_id}/access/restrict
# ---------------------------------------------------------------------------


@router.post(
    "/organizations/{org_id}/clients/{client_id}/access/restrict",
    response_model=ClientAccessSummary,
    summary="Switch a client to restricted access mode",
)
async def restrict_client_access(
    org_id: UUID,
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientAccessSummary:
    """
    Lock down a client: create 'full' access records for ALL active org
    members.  The admin can then selectively change individual access
    levels to 'readonly' or 'none'.
    """
    _require_org_admin(auth, org_id, db)
    _require_org_client(org_id, client_id, db)

    # Get all active members
    active_members = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.is_active.is_(True),
        )
        .all()
    )

    # Get existing access records
    existing_user_ids = set(
        r.user_id
        for r in db.query(ClientAccess.user_id)
        .filter(ClientAccess.client_id == client_id)
        .all()
    )

    # Create records for members who don't have one yet
    for m in active_members:
        if m.user_id not in existing_user_ids:
            db.add(ClientAccess(
                client_id=client_id,
                user_id=m.user_id,
                access_level="full",
                assigned_by=auth.user_id,
            ))

    db.commit()

    # Return the full list
    records = (
        db.query(ClientAccess)
        .filter(ClientAccess.client_id == client_id)
        .all()
    )

    enriched = []
    for rec in records:
        user = db.query(User).filter(User.clerk_id == rec.user_id).first()
        enriched.append(
            ClientAccessResponse(
                id=rec.id,
                client_id=rec.client_id,
                user_id=rec.user_id,
                user_email=user.email if user else None,
                user_name=(
                    " ".join(p for p in (user.first_name, user.last_name) if p)
                    if user else None
                ),
                access_level=rec.access_level,
                assigned_by=rec.assigned_by,
                created_at=rec.created_at,
            )
        )

    return ClientAccessSummary(mode="restricted", records=enriched)
