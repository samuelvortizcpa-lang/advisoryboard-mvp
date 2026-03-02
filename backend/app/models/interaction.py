import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.user import User

# Valid values for the type column
INTERACTION_TYPES = ("call", "email", "meeting", "note")


class Interaction(Base):
    """
    A logged touchpoint with a client (call, email, meeting, or note).

    `date` is when the interaction actually happened (user-supplied);
    `created_at` is when the record was entered into the system.

    `type` is a plain string; valid values: 'call', 'email', 'meeting', 'note'.
    Validation is enforced at the API/service layer, not the DB layer.
    """

    __tablename__ = "interactions"

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
    # Nullable so the record survives if the creator's account is deleted.
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Valid values: 'call', 'email', 'meeting', 'note'
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # When the interaction actually occurred (client-supplied)
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    client: Mapped["Client"] = relationship(
        "Client",
        back_populates="interactions",
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="interactions_created",
        foreign_keys=[created_by],
    )

    def __repr__(self) -> str:
        return (
            f"<Interaction id={self.id} type={self.type!r} "
            f"title={self.title!r} date={self.date.date()}>"
        )
