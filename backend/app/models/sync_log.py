import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("integration_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sync_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    emails_found: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    emails_ingested: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    emails_skipped: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    connection: Mapped["IntegrationConnection"] = relationship(
        "IntegrationConnection", back_populates="sync_logs"
    )
