from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

from app.schemas.client_type import ClientTypeResponse


class ClientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = Field(None, max_length=255)
    business_name: Optional[str] = Field(None, max_length=255)
    entity_type: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=10000)
    client_type_id: Optional[UUID] = None
    custom_instructions: Optional[str] = Field(None, max_length=5000)
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
    is_tax_preparer: Optional[bool] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = Field(None, max_length=255)
    business_name: Optional[str] = Field(None, max_length=255)
    entity_type: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=10000)
    client_type_id: Optional[UUID] = None
    custom_instructions: Optional[str] = Field(None, max_length=5000)
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
    is_tax_preparer: Optional[bool] = None


class ClientResponse(ClientBase):
    id: UUID
    owner_id: UUID
    org_id: Optional[UUID] = None
    created_by: Optional[str] = None
    consent_status: str = "not_required"
    has_tax_documents: bool = False
    data_handling_acknowledged: bool = False
    document_count: int = 0
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


class AssignedMember(BaseModel):
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    role: str = "assigned"


class ClientWithAssignments(ClientResponse):
    assigned_members: list[AssignedMember] = []


class ClientDetailResponse(ClientResponse):
    """Extended response for the single-client detail endpoint."""
    members: list[ClientAccessMember] = []


class ClientListResponse(BaseModel):
    items: list[ClientWithAssignments]
    total: int
    skip: int
    limit: int
