import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TokenUsage(Base):
    """
    Tracks token usage and estimated cost for every AI API call.

    Used for cost monitoring, per-client billing analysis, and pricing decisions.
    """

    __tablename__ = "token_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    # Clerk user ID
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Organization context for aggregating usage at the org level
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Which client context (nullable — some calls like document classification
    # happen in background tasks without a clear user session)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
    )

    # "factual", "strategic", "classification", etc.
    query_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Exact model string (e.g. "gpt-4o-mini", "claude-sonnet-4-6-20250514")
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    estimated_cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 6), nullable=False, default=0
    )

    # Which feature triggered the call (e.g. "chat", "classify", "brief")
    endpoint: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_token_usage_user_created", "user_id", "created_at"),
        Index("ix_token_usage_client_id", "client_id"),
        Index("ix_token_usage_model", "model"),
    )

    def __repr__(self) -> str:
        return (
            f"<TokenUsage id={self.id} model={self.model!r} "
            f"tokens={self.total_tokens} cost=${self.estimated_cost_usd}>"
        )
