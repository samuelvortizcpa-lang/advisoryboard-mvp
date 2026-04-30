"""SQLAlchemy model for cadence_template_deliverables (Layer 2 Gap 4)."""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cadence_template import CadenceTemplate

DELIVERABLE_KEY_VALUES = (
    "kickoff_memo",
    "progress_note",
    "quarterly_memo",
    "mid_year_tune_up",
    "year_end_recap",
    "pre_prep_brief",
    "post_prep_flag",
)


class CadenceTemplateDeliverable(Base):
    __tablename__ = "cadence_template_deliverables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cadence_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    deliverable_key: Mapped[str] = mapped_column(
        PG_ENUM(
            *DELIVERABLE_KEY_VALUES,
            name="deliverable_key",
            create_type=False,
        ),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    template: Mapped["CadenceTemplate"] = relationship(
        "CadenceTemplate", back_populates="deliverables"
    )

    __table_args__ = (
        UniqueConstraint(
            "template_id", "deliverable_key", name="uq_template_deliverable"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CadenceTemplateDeliverable template_id={self.template_id} "
            f"key={self.deliverable_key!r} enabled={self.is_enabled}>"
        )
