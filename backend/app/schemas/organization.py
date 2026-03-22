from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class OrgCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None  # auto-generated if blank


class AddMemberRequest(BaseModel):
    user_email: str
    role: str = "member"


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    org_type: str
    max_members: int
    member_count: int = 0
    role: Optional[str] = None  # the requesting user's role in this org

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
