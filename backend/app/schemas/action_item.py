from datetime import date, datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ActionItemResponse(BaseModel):
    id: UUID
    document_id: Optional[UUID] = None
    client_id: UUID
    text: str
    status: str
    priority: Optional[str]
    due_date: Optional[date]
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    source: str = "ai_extracted"
    engagement_task_id: Optional[UUID] = None
    engagement_workflow_type: Optional[str] = None
    extracted_at: Optional[datetime] = None
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    document_filename: Optional[str] = None
    client_name: Optional[str] = None

    model_config = {"from_attributes": True}


class ActionItemUpdate(BaseModel):
    """Fields the client may change on an existing action item."""
    status: Optional[str] = None       # 'pending' | 'completed' | 'cancelled'
    priority: Optional[str] = None     # 'low' | 'medium' | 'high'
    due_date: Optional[date] = None    # explicit null clears the date
    text: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    notes: Optional[str] = None


class ActionItemCreate(BaseModel):
    """Schema for manually creating an action item."""
    text: str
    client_id: UUID
    priority: Optional[str] = "medium"
    due_date: Optional[date] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    notes: Optional[str] = None


class ActionItemListResponse(BaseModel):
    items: List[ActionItemResponse]
    total: int
    skip: int
    limit: int
