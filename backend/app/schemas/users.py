"""Pydantic schemas for user-related endpoints."""

from typing import List

from pydantic import BaseModel


class OnboardingUpdateRequest(BaseModel):
    completed: bool


class OnboardingUpdateResponse(BaseModel):
    has_completed_onboarding: bool


class TooltipDismissRequest(BaseModel):
    tooltip_id: str
    action: str = "dismiss"


class TooltipDismissResponse(BaseModel):
    dismissed_tooltips: List[str]
