"""
Tests for multi-tenant organization isolation.

Verifies that check_client_access enforces org boundaries:
- Users can only access clients within their own org
- Admins have unrestricted access within their org
- Non-admin members get open access by default (no assignments)
- Cross-org access is always denied
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.models.organization_member import OrganizationMember
from app.services.auth_context import AuthContext, check_client_access
from tests.conftest import make_client, make_org, make_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_membership(
    db,
    *,
    org_id: uuid.UUID,
    user_id: str,
    role: str = "member",
    is_active: bool = True,
) -> OrganizationMember:
    """Create and persist an OrganizationMember row."""
    member = OrganizationMember(
        id=uuid.uuid4(),
        org_id=org_id,
        user_id=user_id,
        role=role,
        is_active=is_active,
        joined_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db.add(member)
    db.flush()
    return member


def build_auth(user_id: str, org_id: uuid.UUID, role: str = "member", is_personal: bool = False) -> AuthContext:
    """Build an AuthContext without going through the FastAPI dependency."""
    return AuthContext(
        user_id=user_id,
        org_id=org_id,
        org_role=role,
        is_personal_org=is_personal,
    )


# ---------------------------------------------------------------------------
# 1. User can access client in their own org
# ---------------------------------------------------------------------------

def test_member_can_access_client_in_own_org(db):
    """A member should be able to access a client that belongs to their org."""
    user = make_user(db)
    org = make_org(db, owner_user_id=user.clerk_id, name="Firm A", org_type="firm")
    make_membership(db, org_id=org.id, user_id=user.clerk_id, role="member")
    client = make_client(db, user, name="Alice Corp", org=org)

    auth = build_auth(user.clerk_id, org.id, role="member")
    result = check_client_access(auth, client.id, db)
    assert result is True


# ---------------------------------------------------------------------------
# 2. User CANNOT access client in a different org (should raise 403)
# ---------------------------------------------------------------------------

def test_user_cannot_access_client_in_different_org(db):
    """Cross-org access must be denied with a 403."""
    user_a = make_user(db, clerk_id="user_alpha", email="alpha@example.com")
    user_b = make_user(db, clerk_id="user_beta", email="beta@example.com")

    org_a = make_org(db, owner_user_id=user_a.clerk_id, name="Firm A", org_type="firm")
    org_b = make_org(db, owner_user_id=user_b.clerk_id, name="Firm B", org_type="firm")

    make_membership(db, org_id=org_a.id, user_id=user_a.clerk_id, role="admin")
    make_membership(db, org_id=org_b.id, user_id=user_b.clerk_id, role="admin")

    # Client belongs to org_b
    client_in_b = make_client(db, user_b, name="Beta Client", org=org_b)

    # User A tries to access client in org B
    auth_a = build_auth(user_a.clerk_id, org_a.id, role="admin")
    with pytest.raises(HTTPException) as exc_info:
        check_client_access(auth_a, client_in_b.id, db)

    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 3. Admin can access any client in their org
# ---------------------------------------------------------------------------

def test_admin_can_access_any_client_in_org(db):
    """An admin should access any client in their org, even one created by another user."""
    owner = make_user(db, clerk_id="user_owner", email="owner@example.com")
    admin = make_user(db, clerk_id="user_admin", email="admin@example.com")

    org = make_org(db, owner_user_id=owner.clerk_id, name="Shared Firm", org_type="firm")
    make_membership(db, org_id=org.id, user_id=owner.clerk_id, role="admin")
    make_membership(db, org_id=org.id, user_id=admin.clerk_id, role="admin")

    # Client created by owner
    client = make_client(db, owner, name="Owner Client", org=org)

    # Admin accesses the client
    auth = build_auth(admin.clerk_id, org.id, role="admin")
    result = check_client_access(auth, client.id, db)
    assert result is True


# ---------------------------------------------------------------------------
# 4. Non-admin member without assignment can access clients (open access)
# ---------------------------------------------------------------------------

def test_non_admin_open_access_by_default(db):
    """When no assignments or client_access records exist, members get open access."""
    owner = make_user(db, clerk_id="user_owner2", email="owner2@example.com")
    member = make_user(db, clerk_id="user_member", email="member@example.com")

    org = make_org(db, owner_user_id=owner.clerk_id, name="Open Firm", org_type="firm")
    make_membership(db, org_id=org.id, user_id=owner.clerk_id, role="admin")
    make_membership(db, org_id=org.id, user_id=member.clerk_id, role="member")

    client = make_client(db, owner, name="Shared Client", org=org)

    # Member (not admin, no explicit assignments) can still access
    auth = build_auth(member.clerk_id, org.id, role="member")
    result = check_client_access(auth, client.id, db)
    assert result is True


# ---------------------------------------------------------------------------
# 5. AuthContext properly scopes by org_id
# ---------------------------------------------------------------------------

def test_auth_context_scopes_org_id(db):
    """
    Verify that AuthContext org_id is used for scoping.
    Even if a client exists in the DB, passing the wrong org_id in AuthContext
    should deny access (simulates a briefs endpoint using org-scoped queries).
    """
    user = make_user(db, clerk_id="user_scoped", email="scoped@example.com")

    org_real = make_org(db, owner_user_id=user.clerk_id, name="Real Org", org_type="firm")
    org_fake = make_org(db, owner_user_id=user.clerk_id, name="Fake Org", org_type="firm")

    make_membership(db, org_id=org_real.id, user_id=user.clerk_id, role="admin")
    make_membership(db, org_id=org_fake.id, user_id=user.clerk_id, role="admin")

    client = make_client(db, user, name="Scoped Client", org=org_real)

    # Access with correct org works
    auth_correct = build_auth(user.clerk_id, org_real.id, role="admin")
    assert check_client_access(auth_correct, client.id, db) is True

    # Access with wrong org (user is admin there too, but client isn't in that org)
    auth_wrong_org = build_auth(user.clerk_id, org_fake.id, role="admin")
    with pytest.raises(HTTPException) as exc_info:
        check_client_access(auth_wrong_org, client.id, db)

    assert exc_info.value.status_code == 403
    assert "don't have access" in exc_info.value.detail
