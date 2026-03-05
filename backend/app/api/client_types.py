from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.client_type import ClientType
from app.schemas.client_type import (
    ClientTypeCreate,
    ClientTypeListResponse,
    ClientTypeResponse,
    ClientTypeUpdate,
)

router = APIRouter()


@router.get("/client-types", response_model=ClientTypeListResponse)
async def list_client_types(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClientTypeListResponse:
    types = db.query(ClientType).order_by(ClientType.name).all()
    return ClientTypeListResponse(types=types, total=len(types))


@router.post(
    "/client-types",
    response_model=ClientTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_client_type(
    data: ClientTypeCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClientTypeResponse:
    existing = db.query(ClientType).filter(ClientType.name == data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Client type '{data.name}' already exists",
        )
    ct = ClientType(**data.model_dump())
    db.add(ct)
    db.commit()
    db.refresh(ct)
    return ct


@router.patch("/client-types/{client_type_id}", response_model=ClientTypeResponse)
async def update_client_type(
    client_type_id: UUID,
    data: ClientTypeUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ClientTypeResponse:
    ct = db.query(ClientType).filter(ClientType.id == client_type_id).first()
    if ct is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client type not found"
        )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ct, field, value)

    db.commit()
    db.refresh(ct)
    return ct


@router.delete("/client-types/{client_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client_type(
    client_type_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    ct = db.query(ClientType).filter(ClientType.id == client_type_id).first()
    if ct is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client type not found"
        )

    DEFAULT_NAMES = {
        "Tax Planning",
        "Financial Advisory",
        "Business Consulting",
        "Audit & Compliance",
        "General",
    }
    if ct.name in DEFAULT_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a default client type",
        )

    db.delete(ct)
    db.commit()
