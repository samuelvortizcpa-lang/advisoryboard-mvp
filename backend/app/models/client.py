import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.action_item import ActionItem
    from app.models.chat_message import ChatMessage
    from app.models.client_brief import ClientBrief
    from app.models.client_type import ClientType
    from app.models.document import Document
    from app.models.interaction import Interaction
    from app.models.organization import Organization
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

    # Organization this client belongs to (nullable during migration)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Clerk user ID of who created this client
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
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

    # Client type (optional — determines AI system prompt)
    client_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Per-client AI instruction override (optional)
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # IRC §7216 consent tracking
    consent_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="not_required"
    )
    has_tax_documents: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

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

    client_type: Mapped[Optional["ClientType"]] = relationship(
        "ClientType",
        foreign_keys=[client_type_id],
        lazy="joined",
    )
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="clients",
        foreign_keys=[owner_id],
    )
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        foreign_keys=[org_id],
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
    action_items: Mapped[List["ActionItem"]] = relationship(
        "ActionItem",
        back_populates="client",
        cascade="all, delete-orphan",
    )
    chat_messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="client",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
    )
    briefs: Mapped[List["ClientBrief"]] = relationship(
        "ClientBrief",
        back_populates="client",
        cascade="all, delete-orphan",
        order_by="ClientBrief.generated_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<Client id={self.id} name={self.name!r} "
            f"business={self.business_name!r}>"
        )
