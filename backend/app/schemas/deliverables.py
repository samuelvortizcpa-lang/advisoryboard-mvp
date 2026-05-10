"""
Pydantic schemas for the deliverable drafting system.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class StrategyReference(BaseModel):
    """A strategy referenced in a deliverable draft."""

    id: str
    name: str


class TaskReference(BaseModel):
    """A client-facing task referenced in a deliverable draft."""

    id: str
    name: str
    owner_role: str
    due_date: Optional[date] = None
    strategy_name: str = ""


class ReferencesPayload(BaseModel):
    """Structured references extracted from a deliverable draft."""

    strategies: list[StrategyReference] = []
    tasks: list[TaskReference] = []


class DeliverableDraftResponse(BaseModel):
    """Response from draft_deliverable — the AI-generated draft + metadata."""

    subject: str
    body: str
    references: ReferencesPayload
    warnings: list[str] = []


class DraftKickoffMemoRequest(BaseModel):
    """Request body for drafting a kickoff memo."""

    tax_year: int


class RecordDeliverableSentRequest(BaseModel):
    """Request body for sending a deliverable via Resend."""

    tax_year: int
    subject: str
    body: str
    recipient_email: str
