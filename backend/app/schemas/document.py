from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    client_id: UUID
    uploaded_by: Optional[UUID]
    filename: str
    file_type: str
    file_size: int
    upload_date: datetime
    processed: bool
    processing_error: Optional[str]

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    skip: int
    limit: int
