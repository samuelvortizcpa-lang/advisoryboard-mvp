from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class OrgCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=100)


class AddMemberRequest(BaseModel):
    user_email: str = Field(..., max_length=255)
    role: str = Field(default="member", max_length=50)


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    org_type: str
    max_members: int
    member_count: int = 0
    role: Optional[str] = None  # the requesting user's role in this org
    default_cadence_template_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class OrgMemberResponse(BaseModel):
    id: UUID
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    role: str
    joined_at: datetime
    is_active: bool

    class Config:
        from_attributes = True
