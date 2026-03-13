from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class ChatSourceItem(BaseModel):
    document_id: str
    filename: str
    preview: str
    score: float = 0.0
    chunk_text: str = ""
    chunk_index: int = 0


class ChatMessageResponse(BaseModel):
    id: UUID
    client_id: UUID
    user_id: Optional[str]
    role: str
    content: str
    sources: Optional[List[ChatSourceItem]]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageResponse]
    total: int
    skip: int
    limit: int
