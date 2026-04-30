"""SQLAlchemy model for cadence_templates (Layer 2 Gap 4)."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cadence_template_deliverable import CadenceTemplateDeliverable
    from app.models.organization import Organization


class CadenceTemplate(Base):
    __tablename__ = "cadence_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    deliverables: Mapped[List["CadenceTemplateDeliverable"]] = relationship(
        "CadenceTemplateDeliverable",
        back_populates="template",
        cascade="all, delete-orphan",
    )
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        foreign_keys=[org_id],
    )

    def __repr__(self) -> str:
        return (
            f"<CadenceTemplate id={self.id} name={self.name!r} "
            f"is_system={self.is_system}>"
        )
