from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ClientTypeBase(BaseModel):
    name: str
    description: str
    system_prompt: str
    color: str


class ClientTypeCreate(ClientTypeBase):
    pass


class ClientTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    color: Optional[str] = None


class ClientTypeResponse(ClientTypeBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ClientTypeListResponse(BaseModel):
    types: List[ClientTypeResponse]
    total: int
