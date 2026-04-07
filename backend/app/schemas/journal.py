from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class JournalEntryCreate(BaseModel):
    """Create a new journal entry."""

    title: str = Field(..., max_length=200)
    content: Optional[str] = None
    entry_type: str = Field("manual", max_length=30)
    category: Optional[str] = Field(None, max_length=50)
    effective_date: Optional[date] = None
    source_type: Optional[str] = Field(None, max_length=30)
    source_id: Optional[UUID] = None
    metadata: Optional[dict[str, Any]] = None
    is_pinned: bool = False


class JournalEntryUpdate(BaseModel):
    """Partial update for a journal entry."""

    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    effective_date: Optional[date] = None
    is_pinned: Optional[bool] = None


class JournalEntryResponse(BaseModel):
    """Full journal entry returned from the API."""

    id: UUID
    client_id: UUID
    user_id: str
    entry_type: str
    category: Optional[str] = None
    title: str
    content: Optional[str] = None
    effective_date: Optional[date] = None
    source_type: Optional[str] = None
    source_id: Optional[UUID] = None
    metadata: Optional[dict[str, Any]] = None
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JournalFeedResponse(BaseModel):
    """Paginated journal feed."""

    entries: list[JournalEntryResponse]
    total: int


class ProfileFlagChange(BaseModel):
    """A single profile flag change record."""

    flag_name: str
    old_value: Optional[bool] = None
    new_value: Optional[bool] = None
    changed_by: Optional[str] = None
    changed_at: datetime
    source: Optional[str] = None

    model_config = {"from_attributes": True}
