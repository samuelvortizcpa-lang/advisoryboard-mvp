import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.interaction import Interaction
    from app.models.user import User


class Client(Base):
    """
    A client that a CPA firm advises.

    Each Client belongs to one User (owner) who is the CPA or firm member
    responsible for that engagement.
    """

    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Who owns / manages this client
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Contact / business info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Valid values: LLC, S-Corp, C-Corp, Partnership, Sole Proprietorship,
    # Individual, Non-Profit, Trust, Other
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    owner: Mapped["User"] = relationship(
        "User",
        back_populates="clients",
        foreign_keys=[owner_id],
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    interactions: Mapped[List["Interaction"]] = relationship(
        "Interaction",
        back_populates="client",
        cascade="all, delete-orphan",
        order_by="Interaction.date.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<Client id={self.id} name={self.name!r} "
            f"business={self.business_name!r}>"
        )
