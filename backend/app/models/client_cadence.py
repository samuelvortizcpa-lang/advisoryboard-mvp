"""SQLAlchemy model for client_cadence (Layer 2 Gap 4)."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cadence_template import CadenceTemplate
    from app.models.client import Client


class ClientCadence(Base):
    __tablename__ = "client_cadence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cadence_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    overrides: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assigned_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    template: Mapped["CadenceTemplate"] = relationship("CadenceTemplate")
    client: Mapped["Client"] = relationship("Client")

    def __repr__(self) -> str:
        return (
            f"<ClientCadence client_id={self.client_id} "
            f"template_id={self.template_id}>"
        )
