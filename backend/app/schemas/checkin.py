import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ── Question schema ───────────────────────────────────────────────────────────


class CheckinQuestionSchema(BaseModel):
    id: str
    text: str
    type: str  # text, textarea, rating, select, multiselect
    options: list[str] | None = None


# ── Template schemas ──────────────────────────────────────────────────────────


class CheckinTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    questions: list[CheckinQuestionSchema]


class CheckinTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    questions: list[CheckinQuestionSchema] | None = None
    is_active: bool | None = None


class CheckinTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID | None = None
    created_by: str | None = None
    name: str
    description: str | None = None
    questions: list[CheckinQuestionSchema]
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Send / submit schemas ────────────────────────────────────────────────────


class CheckinSendRequest(BaseModel):
    template_id: uuid.UUID
    client_email: str
    client_name: str | None = None


class CheckinAnswerSchema(BaseModel):
    question_id: str
    answer: Any


class CheckinSubmitRequest(BaseModel):
    responses: list[CheckinAnswerSchema]


# ── Response schema ──────────────────────────────────────────────────────────


class CheckinResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    template_id: uuid.UUID
    template_name: str
    sent_by: str
    sent_to_email: str
    sent_to_name: str | None = None
    access_token: str
    status: str
    responses: list[CheckinAnswerSchema] | None = None
    response_text: str | None = None
    completed_at: datetime | None = None
    expires_at: datetime
    sent_at: datetime
    created_at: datetime
