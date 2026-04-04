from typing import Optional

from pydantic import BaseModel, Field


class NotificationPreferenceResponse(BaseModel):
    id: str
    user_id: str
    org_id: str
    task_assigned: bool
    task_completed: bool
    deadline_reminder: bool
    deadline_reminder_days: int
    daily_digest: bool

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    task_assigned: Optional[bool] = None
    task_completed: Optional[bool] = None
    deadline_reminder: Optional[bool] = None
    deadline_reminder_days: Optional[int] = Field(default=None, ge=1, le=7)
    daily_digest: Optional[bool] = None
