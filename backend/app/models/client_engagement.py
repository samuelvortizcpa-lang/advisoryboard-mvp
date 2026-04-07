import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.engagement_template import EngagementTemplate


class ClientEngagement(Base):
    """Links a client to an engagement template with optional per-client overrides."""

    __tablename__ = "client_engagements"
    __table_args__ = (
        UniqueConstraint("client_id", "template_id", name="uq_client_engagement"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_templates.id"),
        nullable=False,
    )

    start_year: Mapped[int] = mapped_column(Integer, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False,
    )

    custom_overrides: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────

    client: Mapped["Client"] = relationship("Client")
    template: Mapped["EngagementTemplate"] = relationship("EngagementTemplate")

    def __repr__(self) -> str:
        return (
            f"<ClientEngagement client={self.client_id} "
            f"template={self.template_id} year={self.start_year}>"
        )
