import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.email_template import EmailTemplate


class ClientCommunication(Base):
    """
    Logs every outbound email sent through the platform.

    Each record captures the full rendered content, Resend message ID for
    delivery tracking, and merge variable metadata.
    """

    __tablename__ = "client_communications"

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
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    communication_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="email"
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("email_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="sent"
    )
    resend_message_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # Threading
    thread_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    thread_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    thread_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thread_quarter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    open_items: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    open_items_resolved: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bounced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    client: Mapped["Client"] = relationship("Client", foreign_keys=[client_id])
    template: Mapped[Optional["EmailTemplate"]] = relationship(
        "EmailTemplate", foreign_keys=[template_id]
    )

    def __repr__(self) -> str:
        return (
            f"<ClientCommunication id={self.id} client_id={self.client_id} "
            f"status={self.status!r}>"
        )
