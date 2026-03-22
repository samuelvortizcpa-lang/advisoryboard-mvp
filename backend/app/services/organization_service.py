"""
Organization service — CRUD, personal org auto-creation, and membership management.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_access import ClientAccess
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_slug(email: str) -> str:
    """Generate a URL-friendly slug from an email prefix + 4 random chars."""
    prefix = email.split("@")[0] if "@" in email else email
    # Keep only alphanumeric and hyphens, lowercase
    prefix = "".join(c if c.isalnum() or c == "-" else "-" for c in prefix.lower())
    prefix = prefix.strip("-")[:20]  # cap length
    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return f"{prefix}-{suffix}"


def _ensure_unique_slug(db: Session, slug: str) -> str:
    """If the slug already exists, append random chars until unique."""
    original = slug
    while db.query(Organization.id).filter(Organization.slug == slug).first() is not None:
        suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
        slug = f"{original}-{suffix}"
    return slug


# ---------------------------------------------------------------------------
# 1. get_or_create_personal_org
# ---------------------------------------------------------------------------

def get_or_create_personal_org(
    user_id: str,
    user_email: str,
    user_name: str | None,
    db: Session,
) -> Organization:
    """
    Return the user's personal org, creating one if it doesn't exist.

    Every user gets exactly one personal org the first time they hit any
    org-aware endpoint.
    """
    org = (
        db.query(Organization)
        .filter(
            Organization.owner_user_id == user_id,
            Organization.org_type == "personal",
        )
        .first()
    )
    if org is not None:
        return org

    display = user_name.strip() if user_name and user_name.strip() else user_email
    name = f"{display}'s Workspace"
    slug = _ensure_unique_slug(db, _generate_slug(user_email))

    org = Organization(
        name=name,
        slug=slug,
        owner_user_id=user_id,
        org_type="personal",
        max_members=1,
    )
    db.add(org)
    db.flush()  # get org.id before creating the member row

    member = OrganizationMember(
        org_id=org.id,
        user_id=user_id,
        role="admin",
    )
    db.add(member)
    db.commit()
    db.refresh(org)

    logger.info("Created personal org %s for user %s", org.slug, user_id)
    return org


# ---------------------------------------------------------------------------
# 2. create_firm_org
# ---------------------------------------------------------------------------

def create_firm_org(
    name: str,
    slug: str | None,
    owner_user_id: str,
    clerk_org_id: str | None,
    max_members: int,
    db: Session,
) -> Organization:
    """Create a firm organization and add the owner as admin."""
    if not slug:
        slug = _generate_slug(name)
    slug = _ensure_unique_slug(db, slug)

    org = Organization(
        name=name,
        slug=slug,
        owner_user_id=owner_user_id,
        clerk_org_id=clerk_org_id,
        org_type="firm",
        max_members=max_members,
    )
    db.add(org)
    db.flush()

    member = OrganizationMember(
        org_id=org.id,
        user_id=owner_user_id,
        role="admin",
    )
    db.add(member)
    db.commit()
    db.refresh(org)

    logger.info("Created firm org %s for user %s", org.slug, owner_user_id)
    return org


# ---------------------------------------------------------------------------
# 3. get_user_orgs
# ---------------------------------------------------------------------------

def get_user_orgs(user_id: str, db: Session) -> list[dict]:
    """
    Return all organizations where user is an active member.

    Each result includes the user's role and the org's member count.
    Ordered by org_type (personal first), then name.
    """
    member_count_sq = (
        db.query(
            OrganizationMember.org_id,
            func.count(OrganizationMember.id).label("member_count"),
        )
        .filter(OrganizationMember.is_active.is_(True))
        .group_by(OrganizationMember.org_id)
        .subquery()
    )

    rows = (
        db.query(
            Organization,
            OrganizationMember.role,
            func.coalesce(member_count_sq.c.member_count, 0).label("member_count"),
        )
        .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
        .outerjoin(member_count_sq, member_count_sq.c.org_id == Organization.id)
        .filter(
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active.is_(True),
        )
        .order_by(
            # personal first: 'personal' < 'firm' alphabetically, so asc works
            case(
                (Organization.org_type == "personal", 0),
                else_=1,
            ),
            Organization.name,
        )
        .all()
    )

    return [
        {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "org_type": org.org_type,
            "max_members": org.max_members,
            "member_count": count,
            "role": role,
        }
        for org, role, count in rows
    ]


# ---------------------------------------------------------------------------
# 4. get_org_by_id
# ---------------------------------------------------------------------------

def get_org_by_id(
    org_id: str,
    user_id: str,
    db: Session,
) -> dict | None:
    """Return the org if the user is an active member, else None."""
    member_count = (
        db.query(func.count(OrganizationMember.id))
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.is_active.is_(True),
        )
        .scalar()
    ) or 0

    row = (
        db.query(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
        .filter(
            Organization.id == org_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if row is None:
        return None

    org, role = row
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "org_type": org.org_type,
        "max_members": org.max_members,
        "member_count": member_count,
        "role": role,
    }


# ---------------------------------------------------------------------------
# 5. get_org_members
# ---------------------------------------------------------------------------

def get_org_members(
    org_id: str,
    requesting_user_id: str,
    db: Session,
) -> list[dict] | None:
    """
    Return all active members of the org with user details.

    Returns None if the requesting user is not an active member.
    """
    # Verify the requester is an active member
    requester = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == requesting_user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if requester is None:
        return None

    rows = (
        db.query(OrganizationMember, User.email, User.first_name, User.last_name)
        .outerjoin(User, User.clerk_id == OrganizationMember.user_id)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.is_active.is_(True),
        )
        .order_by(OrganizationMember.joined_at)
        .all()
    )

    results = []
    for member, email, first_name, last_name in rows:
        parts = [p for p in (first_name, last_name) if p]
        user_name = " ".join(parts) if parts else None
        results.append({
            "id": member.id,
            "user_id": member.user_id,
            "user_email": email,
            "user_name": user_name,
            "role": member.role,
            "joined_at": member.joined_at,
            "is_active": member.is_active,
        })

    return results


# ---------------------------------------------------------------------------
# 6. add_member
# ---------------------------------------------------------------------------

def add_member(
    org_id: str,
    user_id: str,
    role: str,
    invited_by: str,
    db: Session,
) -> OrganizationMember | str:
    """
    Add a member to the org.

    Returns the new OrganizationMember on success, or an error string.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        return "org_not_found"

    # Check seat limit
    active_count = (
        db.query(func.count(OrganizationMember.id))
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.is_active.is_(True),
        )
        .scalar()
    ) or 0

    if active_count >= org.max_members:
        return "max_members_reached"

    # Check for existing membership (active or inactive)
    existing = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == user_id,
        )
        .first()
    )
    if existing is not None:
        if existing.is_active:
            return "already_member"
        # Re-activate a previously removed member
        existing.is_active = True
        existing.role = role
        existing.invited_by = invited_by
        existing.invited_at = datetime.now(timezone.utc)
        existing.joined_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        logger.info("Re-activated member %s in org %s", user_id, org_id)
        return existing

    now = datetime.now(timezone.utc)
    member = OrganizationMember(
        org_id=org_id,
        user_id=user_id,
        role=role,
        invited_by=invited_by,
        invited_at=now,
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    logger.info("Added member %s to org %s with role %s", user_id, org_id, role)
    return member


# ---------------------------------------------------------------------------
# 7. update_member_role
# ---------------------------------------------------------------------------

def update_member_role(
    org_id: str,
    target_user_id: str,
    new_role: str,
    requesting_user_id: str,
    db: Session,
) -> OrganizationMember | str:
    """
    Update a member's role. Only admins may do this.

    Returns updated OrganizationMember on success, or an error string.
    """
    # Verify requester is admin
    requester = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == requesting_user_id,
            OrganizationMember.is_active.is_(True),
            OrganizationMember.role == "admin",
        )
        .first()
    )
    if requester is None:
        return "not_admin"

    # Don't allow demoting the org owner
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org and org.owner_user_id == target_user_id and new_role != "admin":
        return "cannot_demote_owner"

    target = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == target_user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if target is None:
        return "member_not_found"

    target.role = new_role
    db.commit()
    db.refresh(target)

    logger.info(
        "Updated role of %s in org %s to %s (by %s)",
        target_user_id, org_id, new_role, requesting_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# 8. remove_member
# ---------------------------------------------------------------------------

def remove_member(
    org_id: str,
    target_user_id: str,
    requesting_user_id: str,
    db: Session,
) -> bool | str:
    """
    Soft-remove a member from the org and revoke their client_access.

    Returns True on success, or an error string.
    """
    # Verify requester is admin
    requester = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == requesting_user_id,
            OrganizationMember.is_active.is_(True),
            OrganizationMember.role == "admin",
        )
        .first()
    )
    if requester is None:
        return "not_admin"

    # Don't allow removing the org owner
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org and org.owner_user_id == target_user_id:
        return "cannot_remove_owner"

    target = (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.org_id == org_id,
            OrganizationMember.user_id == target_user_id,
            OrganizationMember.is_active.is_(True),
        )
        .first()
    )
    if target is None:
        return "member_not_found"

    # Soft-delete the membership
    target.is_active = False

    # Deactivate all client_access for this user within this org's clients
    org_client_ids = (
        db.query(Client.id).filter(Client.org_id == org_id).subquery()
    )
    db.query(ClientAccess).filter(
        ClientAccess.user_id == target_user_id,
        ClientAccess.client_id.in_(org_client_ids),
    ).update({"access_level": "none"}, synchronize_session="fetch")

    db.commit()

    logger.info(
        "Removed member %s from org %s (by %s)",
        target_user_id, org_id, requesting_user_id,
    )
    return True


# ---------------------------------------------------------------------------
# 9. get_active_org_for_user
# ---------------------------------------------------------------------------

def get_active_org_for_user(user_id: str, db: Session) -> Organization | None:
    """
    Resolve the "active" organization for a user.

    Current logic (will be replaced by X-Org-Id header):
      - If user has only 1 org, return it.
      - If user has multiple orgs, return the first firm org.
      - Fall back to personal org.
      - None if user has no orgs at all.
    """
    orgs = (
        db.query(Organization)
        .join(OrganizationMember, OrganizationMember.org_id == Organization.id)
        .filter(
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active.is_(True),
        )
        .order_by(
            case(
                (Organization.org_type == "firm", 0),
                else_=1,
            ),
            Organization.name,
        )
        .all()
    )

    if not orgs:
        return None
    # First firm org if available, otherwise the only (personal) org
    return orgs[0]
