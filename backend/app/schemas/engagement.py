from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EngagementTemplateTaskResponse(BaseModel):
    """A single task within an engagement template."""

    id: UUID
    task_name: str
    category: Optional[str] = None
    recurrence: str
    month: Optional[int] = None
    day: Optional[int] = None
    lead_days: int
    priority: str
    display_order: int

    model_config = {"from_attributes": True}


class EngagementTemplateResponse(BaseModel):
    """An engagement template with its tasks."""

    id: UUID
    name: str
    description: Optional[str] = None
    entity_types: Optional[list[str]] = None
    is_system: bool
    is_active: bool
    tasks: list[EngagementTemplateTaskResponse] = []

    model_config = {"from_attributes": True}


class ClientEngagementResponse(BaseModel):
    """A client's active engagement with a template."""

    id: UUID
    client_id: UUID
    template: EngagementTemplateResponse
    start_year: int
    is_active: bool
    custom_overrides: Optional[dict[str, Any]] = None
    created_at: datetime
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}


class AssignEngagementRequest(BaseModel):
    """Request body for assigning an engagement to a client."""

    template_id: UUID
    start_year: Optional[int] = None
    custom_overrides: Optional[dict[str, Any]] = None


class UpdateEngagementRequest(BaseModel):
    """Request body for updating engagement overrides."""

    custom_overrides: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class CreateTemplateRequest(BaseModel):
    """Request body for creating a custom engagement template."""

    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    entity_types: Optional[list[str]] = None


class GenerateTasksResponse(BaseModel):
    """Response from manual task generation."""

    tasks_created: int
    details: list[dict[str, Any]] = []
