"""
Assignment-based access control.

Opt-in behavior: when an org has made at least one client assignment,
non-admin members are restricted to only their assigned clients.
If no assignments exist in the org, all clients remain visible
(backward compatibility).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client_assignment import ClientAssignment


def get_accessible_client_ids(
    user_id: str,
    org_id: UUID,
    is_admin: bool,
    db: Session,
) -> list[UUID] | None:
    """
    Returns list of client IDs the user can access, or None if no filtering
    is needed.

    None means "show all org clients" — returned when the user is an admin
    or when the org has not yet created any client assignments (backward compat).

    A list (possibly empty) means "restrict to exactly these client IDs".
    """
    if is_admin:
        return None  # admins see everything

    # Check if the org has opted in to assignment-based access
    # by creating at least one assignment
    has_assignments = (
        db.query(ClientAssignment.id)
        .filter(ClientAssignment.org_id == org_id)
        .limit(1)
        .first()
    ) is not None

    if not has_assignments:
        return None  # no assignments yet — backward compat, show all

    # Org has assignments: return only this user's assigned client IDs
    rows = (
        db.query(ClientAssignment.client_id)
        .filter(
            ClientAssignment.user_id == user_id,
            ClientAssignment.org_id == org_id,
        )
        .all()
    )
    return [r.client_id for r in rows]
