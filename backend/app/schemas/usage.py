from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class UsageRecordResponse(BaseModel):
    id: UUID
    created_at: datetime
    endpoint: Optional[str] = None
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    client_id: Optional[UUID] = None
    client_name: Optional[str] = None

    class Config:
        from_attributes = True


class UsageHistoryResponse(BaseModel):
    items: list[UsageRecordResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class ModelStats(BaseModel):
    queries: int
    tokens: int
    cost: float


class DailyUsageResponse(BaseModel):
    date: str
    total_queries: int
    total_tokens: int
    total_cost: float
    by_model: dict[str, ModelStats]


class ClientUsageResponse(BaseModel):
    client_id: UUID
    client_name: str
    total_queries: int
    total_tokens: int
    total_cost: float
    last_query_at: datetime
