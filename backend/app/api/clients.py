from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.client import (
    ClientCreate,
    ClientDetailResponse,
    ClientListResponse,
    ClientResponse,
    ClientUpdate,
)
from app.services import client_service
from app.services.auth_context import AuthContext, check_client_access, get_auth
from app.services.subscription_service import check_client_limit

router = APIRouter()


@router.get("/clients", response_model=ClientListResponse)
async def list_clients(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    assigned_to_me: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientListResponse:
    clients, total = client_service.get_clients(
        db,
        org_id=auth.org_id,
        user_id=auth.user_id,
        org_role=auth.org_role,
        skip=skip,
        limit=limit,
        assigned_to_me=assigned_to_me or False,
    )
    return ClientListResponse(items=clients, total=total, skip=skip, limit=limit)


@router.post("/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientResponse:
    limit_check = check_client_limit(db, auth.user_id, org_id=auth.org_id)
    if not limit_check["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client limit reached. Upgrade your plan to add more clients.",
        )
    return client_service.create_client(
        db,
        data=data,
        org_id=auth.org_id,
        created_by=auth.user_id,
    )


@router.get("/clients/{client_id}", response_model=ClientDetailResponse)
async def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientDetailResponse:
    check_client_access(auth, client_id, db)
    client = client_service.get_client_detail(
        db, client_id=client_id, org_id=auth.org_id
    )
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.put("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: UUID,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> ClientResponse:
    check_client_access(auth, client_id, db)
    # Readonly members cannot update
    if auth.org_role != "admin":
        client_service.require_write_access(db, client_id, auth.user_id)
    client = client_service.update_client(
        db, client_id=client_id, data=data, org_id=auth.org_id
    )
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return client


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth),
) -> None:
    check_client_access(auth, client_id, db)
    client_service.authorize_delete(db, client_id, auth)
    deleted = client_service.delete_client(db, client_id=client_id, org_id=auth.org_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
