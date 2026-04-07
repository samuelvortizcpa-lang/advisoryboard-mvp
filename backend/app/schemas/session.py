from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.chat_message import ChatMessageResponse


# ---------------------------------------------------------------------------
# Session responses
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    """Lightweight session representation for list views."""
    id: UUID
    title: Optional[str]
    summary: Optional[str]
    key_topics: Optional[List[str]]
    key_decisions: Optional[List[str]]
    started_at: datetime
    ended_at: Optional[datetime]
    message_count: int

    model_config = {"from_attributes": True}


class SessionDetail(SessionSummary):
    """Full session with messages."""
    messages: List[ChatMessageResponse]


class SessionListResponse(BaseModel):
    sessions: List[SessionSummary]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SessionSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    limit: int = Field(default=5, ge=1, le=20)


class SessionSearchResult(SessionSummary):
    similarity_score: float


class QAPairResult(BaseModel):
    question: str
    answer: str
    session_id: UUID
    session_title: Optional[str]
    session_date: Optional[datetime]
    similarity_score: float


class SessionSearchResponse(BaseModel):
    sessions: List[SessionSearchResult]
    qa_pairs: List[QAPairResult]
