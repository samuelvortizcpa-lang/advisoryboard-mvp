"""
Client group resolution for the client-linking feature.

Resolves the full linked group for a given client_id.  Links are always
human→entity, so the topology is a star (one human center, N entity
leaves).  No recursive CTE is needed — a single-hop UNION suffices and
avoids the shared-entity traversal bug where a recursive CTE would
follow: Michael → Acme → Bob.

See client-linking-architecture.md for design rationale.
"""

from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session


# TODO: Add request-scoped caching once a pattern is established.
# No existing request-scoped cache pattern found in the codebase (only
# module-level TTL caches in alerts_service.py and dashboard.py).
# For Stage 1, this function runs a fresh query each call.


def resolve_client_group(client_id: UUID, db: Session) -> list[UUID]:
    """Return all client IDs in the linked group starting from *client_id*.

    Only follows links where ``confirmed_by_user = TRUE`` **and**
    ``dismissed_at IS NULL``.  A dismissed link (even if still marked
    confirmed) is treated as inactive — the safer default for Stage 1.

    The starting *client_id* is always included, even when it has no
    confirmed links (the solo-client case).

    Privacy invariant: when two humans (Michael, Bob) both link to a
    shared entity (Acme), Michael's group = {Michael, Acme} and Bob's
    group = {Bob, Acme}.  Humans never traverse through a shared entity
    to reach each other.  This is enforced by doing exactly one hop in
    each direction rather than a recursive traversal.
    """
    stmt = text("""
        SELECT :start_id AS client_id
        UNION
        SELECT cl.entity_client_id
        FROM client_links cl
        WHERE cl.human_client_id = :start_id
          AND cl.confirmed_by_user = TRUE
          AND cl.dismissed_at IS NULL
        UNION
        SELECT cl.human_client_id
        FROM client_links cl
        WHERE cl.entity_client_id = :start_id
          AND cl.confirmed_by_user = TRUE
          AND cl.dismissed_at IS NULL
    """).bindparams(bindparam("start_id", type_=PG_UUID(as_uuid=True)))

    result = db.execute(stmt, {"start_id": client_id})
    return [
        row[0] if isinstance(row[0], UUID) else UUID(row[0])
        for row in result
    ]
