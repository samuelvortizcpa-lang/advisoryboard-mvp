from typing import List, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate


def get_clients(
    db: Session,
    owner_id: UUID,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Client], int]:
    """Return a page of clients owned by owner_id and the total row count."""
    query = db.query(Client).filter(Client.owner_id == owner_id)
    total = query.count()
    clients = (
        query.order_by(Client.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return clients, total


def get_client(db: Session, client_id: UUID, owner_id: UUID) -> Client | None:
    """Return the client only if it belongs to owner_id, else None."""
    return (
        db.query(Client)
        .filter(Client.id == client_id, Client.owner_id == owner_id)
        .first()
    )


def create_client(db: Session, data: ClientCreate, owner_id: UUID) -> Client:
    """Create and persist a new client."""
    client = Client(**data.model_dump(), owner_id=owner_id)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def update_client(
    db: Session,
    client_id: UUID,
    data: ClientUpdate,
    owner_id: UUID,
) -> Client | None:
    """
    Update only the fields supplied in `data` (partial update).
    Returns None when the client doesn't exist or isn't owned by owner_id.
    """
    client = get_client(db, client_id, owner_id)
    if client is None:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    return client


def delete_client(db: Session, client_id: UUID, owner_id: UUID) -> bool:
    """
    Delete the client if owned by owner_id.
    Returns True on success, False when not found or not owned.
    """
    client = get_client(db, client_id, owner_id)
    if client is None:
        return False

    db.delete(client)
    db.commit()
    return True
