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
    # Tax strategy profile flags
    has_business_entity: bool = False
    has_real_estate: bool = False
    is_real_estate_professional: bool = False
    has_high_income: bool = False
    has_estate_planning: bool = False
    is_medical_professional: bool = False
    has_retirement_plans: bool = False
    has_investments: bool = False
    has_employees: bool = False


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
    # Tax strategy profile flags
    has_business_entity: Optional[bool] = None
    has_real_estate: Optional[bool] = None
    is_real_estate_professional: Optional[bool] = None
    has_high_income: Optional[bool] = None
    has_estate_planning: Optional[bool] = None
    is_medical_professional: Optional[bool] = None
    has_retirement_plans: Optional[bool] = None
    has_investments: Optional[bool] = None
    has_employees: Optional[bool] = None


class ClientResponse(ClientBase):
    id: UUID
    owner_id: UUID
    org_id: Optional[UUID] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    client_type: Optional[ClientTypeResponse] = None

    class Config:
        from_attributes = True


class ClientAccessMember(BaseModel):
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    access_level: str

    class Config:
        from_attributes = True


class ClientDetailResponse(ClientResponse):
    """Extended response for the single-client detail endpoint."""
    members: list[ClientAccessMember] = []


class ClientListResponse(BaseModel):
    items: list[ClientResponse]
    total: int
    skip: int
    limit: int
