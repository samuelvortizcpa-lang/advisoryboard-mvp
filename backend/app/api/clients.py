from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.schemas.client import (
    ClientCreate,
    ClientListResponse,
    ClientResponse,
    ClientUpdate,
)
from app.services import client_service, user_service
from app.services.subscription_service import check_client_limit

router = APIRouter()

# ---------------------------------------------------------------------------
# Note on @require_auth vs Depends(get_current_user)
# ---------------------------------------------------------------------------
# The @require_auth decorator injects `current_user` by modifying the
# wrapper's __signature__.  It only does this when `current_user` is NOT
# already declared in the function; but without that declaration the
# function body can't reference the variable.  The explicit
# `Depends(get_current_user)` pattern is the idiomatic FastAPI solution —
# it's what @require_auth wraps internally, and it avoids the edge case.
# ---------------------------------------------------------------------------


@router.get("/clients", response_model=ClientListResponse)
async def list_clients(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClientListResponse:
    user = user_service.get_or_create_user(db, current_user)
    clients, total = client_service.get_clients(
        db, owner_id=user.id, skip=skip, limit=limit
    )
    return ClientListResponse(items=clients, total=total, skip=skip, limit=limit)


@router.post("/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClientResponse:
    user = user_service.get_or_create_user(db, current_user)
    limit_check = check_client_limit(db, user.clerk_id, user.id)
    if not limit_check["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client limit reached. Upgrade your plan to add more clients.",
        )
    return client_service.create_client(db, data=data, owner_id=user.id)


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClientResponse:
    user = user_service.get_or_create_user(db, current_user)
    client = client_service.get_client(db, client_id=client_id, owner_id=user.id)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.put("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClientResponse:
    user = user_service.get_or_create_user(db, current_user)
    client = client_service.update_client(
        db, client_id=client_id, data=data, owner_id=user.id
    )
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    user = user_service.get_or_create_user(db, current_user)
    deleted = client_service.delete_client(db, client_id=client_id, owner_id=user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
