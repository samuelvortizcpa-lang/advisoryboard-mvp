from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ActionItemResponse(BaseModel):
    id: UUID
    document_id: UUID
    client_id: UUID
    text: str
    status: str
    priority: Optional[str]
    due_date: Optional[date]
    extracted_at: datetime
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    document_filename: Optional[str] = None

    model_config = {"from_attributes": True}


class ActionItemUpdate(BaseModel):
    """Fields the client may change on an existing action item."""
    status: Optional[str] = None       # 'pending' | 'completed' | 'cancelled'
    priority: Optional[str] = None     # 'low' | 'medium' | 'high'
    due_date: Optional[date] = None    # explicit null clears the date


class ActionItemListResponse(BaseModel):
    items: List[ActionItemResponse]
    total: int
    skip: int
    limit: int
