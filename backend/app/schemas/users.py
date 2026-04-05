"""Pydantic schemas for user-related endpoints."""

from pydantic import BaseModel


class OnboardingUpdateRequest(BaseModel):
    completed: bool


class OnboardingUpdateResponse(BaseModel):
    has_completed_onboarding: bool
