import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.engagement_template import EngagementTemplate
    from app.models.email_template import EmailTemplate


class EngagementTemplateTask(Base):
    """
    A single recurring task within an engagement template.
    Defines what needs to happen, when, and how far in advance to create it.
    """

    __tablename__ = "engagement_template_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_name: Mapped[str] = mapped_column(String(300), nullable=False)

    category: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )  # quarterly_estimate, annual_return, extension, planning, compliance, review

    recurrence: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )  # annual, quarterly, monthly, one_time

    month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    lead_days: Mapped[int] = mapped_column(
        Integer, server_default="21", nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(10), server_default="medium", nullable=False,
    )

    linked_email_template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("email_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    display_order: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────

    template: Mapped["EngagementTemplate"] = relationship(
        "EngagementTemplate", back_populates="tasks",
    )

    linked_email_template: Mapped[Optional["EmailTemplate"]] = relationship(
        "EmailTemplate",
    )

    def __repr__(self) -> str:
        return f"<EngagementTemplateTask {self.task_name!r} ({self.recurrence})>"
