from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.context_assembler import ContextPurpose


class ContextPurposeEnum(str):
    """Valid context purpose values — mirrors ContextPurpose enum."""

    CHAT = ContextPurpose.CHAT.value
    EMAIL_DRAFT = ContextPurpose.EMAIL_DRAFT.value
    ENGAGEMENT_KICKOFF = ContextPurpose.ENGAGEMENT_KICKOFF.value
    QUARTERLY_ESTIMATE = ContextPurpose.QUARTERLY_ESTIMATE.value
    BRIEF = ContextPurpose.BRIEF.value
    STRATEGY_SUGGEST = ContextPurpose.STRATEGY_SUGGEST.value
    GENERAL = ContextPurpose.GENERAL.value


class ContextRequest(BaseModel):
    purpose: str = Field(
        default="general",
        description=(
            "Context purpose: chat, email_draft, quarterly_estimate, "
            "brief, strategy_suggest, general"
        ),
    )
    options: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            'Purpose-specific options. e.g. {"query": "..."} for chat, '
            '{"tax_year": 2026, "quarter": 2} for quarterly_estimate'
        ),
    )


class ClientContextResponse(BaseModel):
    client_profile: dict[str, Any]
    documents_summary: list[dict[str, Any]] = []
    financial_metrics: Optional[dict[str, Any]] = None
    action_items: list[dict[str, Any]] = []
    communication_history: list[dict[str, Any]] = []
    journal_entries: Optional[list[dict[str, Any]]] = None
    strategy_status: Optional[dict[str, Any]] = None
    engagement_calendar: Optional[list[dict[str, Any]]] = None
    rag_chunks: Optional[list[dict[str, Any]]] = None
