import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EngagementTemplate(Base):
    """
    Defines a type of client engagement (e.g. 1040 Individual, 1120-S S-Corp).
    System templates are seeded; users can create custom ones.
    """

    __tablename__ = "engagement_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    entity_types: Mapped[Optional[list[str]]] = mapped_column(
        JSONB, nullable=True,
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False,
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────

    tasks: Mapped[list["EngagementTemplateTask"]] = relationship(
        "EngagementTemplateTask",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="EngagementTemplateTask.display_order",
    )

    def __repr__(self) -> str:
        return f"<EngagementTemplate {self.name!r}>"
