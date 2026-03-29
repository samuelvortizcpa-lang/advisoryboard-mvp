import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClientConsent(Base):
    """
    IRC Section 7216 consent record.

    Tracks taxpayer consent for disclosure/use of tax return information
    by CPA firms through Callwen.
    """

    __tablename__ = "client_consents"

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

    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    consent_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    consent_tier: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="full_7216"
    )

    consent_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expiration_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    consent_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    taxpayer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preparer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preparer_firm: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    form_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # E-signature fields
    signing_token: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    signing_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_to_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signer_ip_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signer_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signer_typed_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    signed_pdf_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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

    def __repr__(self) -> str:
        return (
            f"<ClientConsent id={self.id} client_id={self.client_id} "
            f"type={self.consent_type!r} status={self.status!r}>"
        )
