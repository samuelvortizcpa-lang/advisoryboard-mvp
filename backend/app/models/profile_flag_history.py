import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client


class ProfileFlagHistory(Base):
    """Records when a client profile flag is toggled and by whom."""

    __tablename__ = "client_profile_flag_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    flag_name: Mapped[str] = mapped_column(String(50), nullable=False)

    old_value: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    new_value: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    changed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    source: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True,
    )  # manual, auto, system

    # ── Relationships ──────────────────────────────────────────────────────

    client: Mapped["Client"] = relationship("Client")

    def __repr__(self) -> str:
        return (
            f"<ProfileFlagHistory {self.flag_name}: "
            f"{self.old_value} → {self.new_value}>"
        )
