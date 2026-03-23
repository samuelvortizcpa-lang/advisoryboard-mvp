import logging
from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.client_access import ClientAccess
from app.models.document import Document
from app.models.user import User
from app.schemas.client import ClientCreate, ClientUpdate
from app.services import storage_service
from app.services.assignment_service import get_accessible_client_ids

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_in_org_filter(org_id: UUID):
    """
    Filter clause for clients in an org.

    Backward-compatible: matches clients with org_id set to the given org,
    OR clients with org_id=NULL that are owned by anyone (pre-migration rows
    are still visible to their owner via the old owner_id path).
    """
    return Client.org_id == org_id


def _client_visible_to_user(org_id: UUID, user_id: str, org_role: str):
    """
    Build a filter for clients this user can see within their org.

    Admins see all clients in the org. Members see clients where:
      (a) no client_access records exist (open by default), OR
      (b) they have a client_access record with access_level != 'none'.
    """
    # This is applied at the query level in get_clients
    return _client_in_org_filter(org_id)


# ---------------------------------------------------------------------------
# List clients
# ---------------------------------------------------------------------------

def get_clients(
    db: Session,
    org_id: UUID,
    user_id: str,
    org_role: str,
    skip: int = 0,
    limit: int = 50,
    assigned_to_me: bool = False,
    # Backward-compat: old callers may still pass owner_id
    owner_id: UUID | None = None,
) -> Tuple[List[Client], int]:
    """Return a page of clients visible to the user within their org."""

    # Backward compat: if caller still uses the old owner_id pattern
    if owner_id is not None and org_id is None:
        query = db.query(Client).filter(Client.owner_id == owner_id)
        total = query.count()
        clients = (
            query.order_by(Client.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return clients, total

    query = db.query(Client).filter(_client_in_org_filter(org_id))

    # ── Assignment-based access control (opt-in) ──────────────────────
    # When the org has made at least one client assignment, non-admin
    # members only see their assigned clients.  If no assignments exist
    # yet, all org clients remain visible (backward compat).
    accessible_ids = get_accessible_client_ids(user_id, org_id, org_role == "admin", db)
    if accessible_ids is not None:
        query = query.filter(Client.id.in_(accessible_ids))
    elif assigned_to_me:
        # Only clients the user has an explicit client_access record for
        query = query.join(
            ClientAccess,
            (ClientAccess.client_id == Client.id)
            & (ClientAccess.user_id == user_id)
            & (ClientAccess.access_level != "none"),
        )
    elif org_role != "admin":
        # Non-admins: filter to clients they can access via client_access
        # A client is accessible if:
        #   - it has NO client_access records at all (open), OR
        #   - the user has a client_access entry with access_level != 'none'
        user_access = (
            db.query(ClientAccess.client_id)
            .filter(
                ClientAccess.user_id == user_id,
                ClientAccess.access_level != "none",
            )
            .subquery()
        )
        has_any_access = (
            db.query(ClientAccess.client_id)
            .group_by(ClientAccess.client_id)
            .subquery()
        )

        query = query.filter(
            or_(
                # No access records exist for this client (open)
                ~Client.id.in_(
                    db.query(has_any_access.c.client_id)
                ),
                # User has explicit access
                Client.id.in_(
                    db.query(user_access.c.client_id)
                ),
            )
        )

    total = query.count()
    clients = (
        query.order_by(Client.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return clients, total


# ---------------------------------------------------------------------------
# Get single client (simple — for backward compat and internal use)
# ---------------------------------------------------------------------------

def get_client(
    db: Session,
    client_id: UUID,
    owner_id: UUID | None = None,
    org_id: UUID | None = None,
) -> Client | None:
    """
    Return a client by ID, scoped to either org_id or owner_id.

    Backward-compatible: if org_id is provided, use it; otherwise fall back
    to the old owner_id filter.
    """
    if org_id is not None:
        return (
            db.query(Client)
            .filter(Client.id == client_id, _client_in_org_filter(org_id))
            .first()
        )
    # Legacy path
    return (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Get client detail (with members list for the detail page)
# ---------------------------------------------------------------------------

def get_client_detail(db: Session, client_id: UUID, org_id: UUID) -> dict | None:
    """Return client with access member list for the detail endpoint."""
    client = (
        db.query(Client)
        .filter(Client.id == client_id, _client_in_org_filter(org_id))
        .first()
    )
    if client is None:
        return None

    # Fetch members with access
    rows = (
        db.query(ClientAccess, User.email, User.first_name, User.last_name)
        .outerjoin(User, User.clerk_id == ClientAccess.user_id)
        .filter(
            ClientAccess.client_id == client_id,
            ClientAccess.access_level != "none",
        )
        .all()
    )

    members = []
    for access, email, first_name, last_name in rows:
        parts = [p for p in (first_name, last_name) if p]
        members.append({
            "user_id": access.user_id,
            "user_email": email,
            "user_name": " ".join(parts) if parts else None,
            "access_level": access.access_level,
        })

    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "business_name": client.business_name,
        "entity_type": client.entity_type,
        "industry": client.industry,
        "notes": client.notes,
        "client_type_id": client.client_type_id,
        "custom_instructions": client.custom_instructions,
        "owner_id": client.owner_id,
        "org_id": client.org_id,
        "created_by": client.created_by,
        "created_at": client.created_at,
        "updated_at": client.updated_at,
        "client_type": client.client_type,
        "members": members,
    }


# ---------------------------------------------------------------------------
# Create client
# ---------------------------------------------------------------------------

def create_client(
    db: Session,
    data: ClientCreate,
    org_id: UUID | None = None,
    created_by: str | None = None,
    # Backward-compat: old callers may still pass owner_id directly
    owner_id: UUID | None = None,
) -> Client:
    """Create a new client and auto-assign access to the creating user."""
    fields = data.model_dump()

    if org_id is not None:
        fields["org_id"] = org_id
        fields["created_by"] = created_by

        # Resolve owner_id from the creating user's Clerk ID for backward compat
        user = db.query(User).filter(User.clerk_id == created_by).first()
        if user:
            fields["owner_id"] = user.id
        elif owner_id:
            fields["owner_id"] = owner_id
    else:
        # Legacy path
        fields["owner_id"] = owner_id

    client = Client(**fields)
    db.add(client)
    db.flush()

    # Auto-create a client_access record for the creator
    if created_by:
        access = ClientAccess(
            client_id=client.id,
            user_id=created_by,
            access_level="full",
            assigned_by=created_by,
        )
        db.add(access)

    db.commit()
    db.refresh(client)
    return client


# ---------------------------------------------------------------------------
# Update client
# ---------------------------------------------------------------------------

def update_client(
    db: Session,
    client_id: UUID,
    data: ClientUpdate,
    owner_id: UUID | None = None,
    org_id: UUID | None = None,
) -> Client | None:
    """
    Partial update. Accepts org_id (new) or owner_id (legacy) for scoping.
    """
    client = get_client(db, client_id, owner_id=owner_id, org_id=org_id)
    if client is None:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    return client


def require_write_access(db: Session, client_id: UUID, user_id: str) -> None:
    """Raise 403 if the user only has readonly access to this client."""
    access = (
        db.query(ClientAccess)
        .filter(
            ClientAccess.client_id == client_id,
            ClientAccess.user_id == user_id,
        )
        .first()
    )
    # No access record = open access (writable)
    if access is None:
        return
    if access.access_level == "readonly":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have readonly access to this client",
        )


# ---------------------------------------------------------------------------
# Delete client
# ---------------------------------------------------------------------------

def authorize_delete(db: Session, client_id: UUID, auth) -> None:
    """
    Only admins or the user who created the client can delete it.
    Raises 403 otherwise.
    """
    if auth.org_role == "admin":
        return
    client = db.query(Client).filter(Client.id == client_id).first()
    if client and client.created_by == auth.user_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only admins or the client creator can delete clients",
    )


def delete_client(
    db: Session,
    client_id: UUID,
    owner_id: UUID | None = None,
    org_id: UUID | None = None,
) -> bool:
    """
    Delete the client. Removes storage files before CASCADE.
    Accepts org_id (new) or owner_id (legacy) for scoping.
    """
    client = get_client(db, client_id, owner_id=owner_id, org_id=org_id)
    if client is None:
        return False

    # Remove files from Supabase Storage before CASCADE deletes DB records
    documents = db.query(Document).filter(Document.client_id == client_id).all()
    for doc in documents:
        if doc.file_path:
            try:
                storage_service.delete_file(doc.file_path)
            except Exception:
                logger.warning("Failed to delete storage file %s", doc.file_path)

    db.delete(client)
    db.commit()
    return True
