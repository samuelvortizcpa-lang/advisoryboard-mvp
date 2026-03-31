from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Communications
# ---------------------------------------------------------------------------


class CommunicationSendRequest(BaseModel):
    subject: str = Field(..., max_length=500)
    body_html: str
    recipient_email: str = Field(..., max_length=255)
    recipient_name: Optional[str] = Field(None, max_length=255)
    template_id: Optional[UUID] = None
    follow_up_days: Optional[int] = Field(None, ge=1, le=90)
    metadata: Optional[Dict[str, Any]] = None


class CommunicationResponse(BaseModel):
    id: UUID
    client_id: UUID
    user_id: str
    communication_type: str
    subject: str
    body_html: str
    body_text: Optional[str]
    recipient_email: str
    recipient_name: Optional[str]
    template_id: Optional[UUID]
    status: str
    resend_message_id: Optional[str]
    metadata: Optional[Dict[str, Any]] = Field(None, alias="metadata_")
    sent_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class FollowUpReminderResponse(BaseModel):
    id: UUID
    communication_id: UUID
    client_id: UUID
    user_id: str
    remind_at: datetime
    status: str
    triggered_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class CommunicationSendResponse(BaseModel):
    communication: CommunicationResponse
    follow_up: Optional[FollowUpReminderResponse] = None


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class RenderTemplateRequest(BaseModel):
    template_id: UUID
    extra_vars: Optional[Dict[str, str]] = None


class RenderedTemplate(BaseModel):
    subject: str
    body_html: str


# ---------------------------------------------------------------------------
# Templates CRUD
# ---------------------------------------------------------------------------


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    subject_template: str = Field(..., max_length=500)
    body_template: str
    template_type: str = Field(..., max_length=50)


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    subject_template: Optional[str] = Field(None, max_length=500)
    body_template: Optional[str] = None
    template_type: Optional[str] = Field(None, max_length=50)


class TemplateResponse(BaseModel):
    id: UUID
    user_id: Optional[str]
    name: str
    subject_template: str
    body_template: str
    template_type: str
    is_default: bool
    is_active: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# AI Draft
# ---------------------------------------------------------------------------


class DraftEmailRequest(BaseModel):
    purpose: str = Field(..., max_length=500)
    additional_context: Optional[str] = Field(None, max_length=2000)


class DraftEmailResponse(BaseModel):
    subject: str
    body_html: str
    body_text: str
    ai_drafted: bool = True


# ---------------------------------------------------------------------------
# Scheduling URL
# ---------------------------------------------------------------------------


class SchedulingUrlUpdate(BaseModel):
    scheduling_url: Optional[str] = Field(None, max_length=500)


class SchedulingUrlResponse(BaseModel):
    scheduling_url: Optional[str]
