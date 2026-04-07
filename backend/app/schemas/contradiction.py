from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContradictionResponse(BaseModel):
    id: UUID
    client_id: UUID
    user_id: str
    org_id: Optional[UUID]
    contradiction_type: str
    severity: str
    title: str
    description: str
    field_name: Optional[str]
    value_a: Optional[Decimal]
    value_b: Optional[Decimal]
    source_a_type: Optional[str]
    source_a_id: Optional[UUID]
    source_a_label: Optional[str]
    source_b_type: Optional[str]
    source_b_id: Optional[UUID]
    source_b_label: Optional[str]
    tax_year: Optional[int]
    status: str
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    resolution_note: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ContradictionListResponse(BaseModel):
    contradictions: List[ContradictionResponse]
    total: int


class ContradictionUpdate(BaseModel):
    status: Optional[str] = None
    resolution_note: Optional[str] = None
    severity: Optional[str] = None


class ContradictionScanResult(BaseModel):
    """Result of running a contradiction scan for a client."""
    new_contradictions: int = 0
    total_open: int = 0
    contradictions: List[ContradictionResponse] = Field(default_factory=list)
