from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union
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


TimelineItem = Annotated[
    Union[DocumentTimelineItem, ActionItemTimelineItem],
    Field(discriminator="type"),
]


class TimelineResponse(BaseModel):
    items: List[TimelineItem]
    total: int
    skip: int
    limit: int
