from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentTimelineItem(BaseModel):
    type: Literal["document"] = "document"
    id: UUID
    date: datetime
    filename: str
    file_type: str
    file_size: int
    processed: bool

    model_config = {"from_attributes": True}


class ActionItemTimelineItem(BaseModel):
    type: Literal["action_item"] = "action_item"
    id: UUID
    date: datetime
    text: str
    status: str
    priority: Optional[str] = None
    source_doc: Optional[str] = None

    model_config = {"from_attributes": True}


class CommunicationTimelineItem(BaseModel):
    type: Literal["communication"] = "communication"
    id: UUID
    date: datetime
    title: str
    subtitle: str
    icon_hint: str = "email"
    metadata: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class SessionTimelineItem(BaseModel):
    type: Literal["session"] = "session"
    id: UUID
    date: datetime
    title: Optional[str] = None
    ended_at: Optional[datetime] = None
    message_count: int = 0
    topic_count: int = 0
    icon_hint: str = "chat"

    model_config = {"from_attributes": True}


class CheckinTimelineItem(BaseModel):
    type: Literal["checkin"] = "checkin"
    id: UUID
    date: datetime
    title: str
    subtitle: str
    icon_hint: str = "mail"
    color: str = "#5bb8af"
    status: str

    model_config = {"from_attributes": True}


TimelineItem = Annotated[
    Union[DocumentTimelineItem, ActionItemTimelineItem, CommunicationTimelineItem, SessionTimelineItem, CheckinTimelineItem],
    Field(discriminator="type"),
]


class TimelineResponse(BaseModel):
    items: List[TimelineItem]
    total: int
    skip: int
    limit: int
