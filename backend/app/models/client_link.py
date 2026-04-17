import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ClientLink(Base):
    """
    A directional link from an individual (human) client to a business/trust
    entity client.  Links are metadata only — no data moves between clients.

    See client-linking-architecture.md for invariants and design rationale.
    """

    __tablename__ = "client_links"
    __table_args__ = (
        UniqueConstraint("human_client_id", "entity_client_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    human_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 'owner_of' | 'partner_in' | 'beneficiary_of' | 'officer_of'
    link_type: Mapped[str] = mapped_column(Text, nullable=False)

    ownership_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True
    )

    # 'firm_files' | 'k1_only' | 'external_cpa' | 'advised_only' | 'unknown'
    filing_responsibility: Mapped[str] = mapped_column(Text, nullable=False)

    confirmed_by_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # 'address_match' | 'name_match' | 'ein_match' | 'k1_issuer_match' | 'manual'
    detection_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detection_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(precision=3, scale=2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    human_client = relationship("Client", foreign_keys=[human_client_id])
    entity_client = relationship("Client", foreign_keys=[entity_client_id])

    def __repr__(self) -> str:
        return (
            f"<ClientLink {self.human_client_id} "
            f"--[{self.link_type}]--> {self.entity_client_id}>"
        )
