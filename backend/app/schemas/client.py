from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.schemas.client_type import ClientTypeResponse


class ClientBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    business_name: Optional[str] = None
    entity_type: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    client_type_id: Optional[UUID] = None
    custom_instructions: Optional[str] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    business_name: Optional[str] = None
    entity_type: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    client_type_id: Optional[UUID] = None
    custom_instructions: Optional[str] = None


class ClientResponse(ClientBase):
    id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    client_type: Optional[ClientTypeResponse] = None

    class Config:
        from_attributes = True


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
    skip: int
    limit: int
