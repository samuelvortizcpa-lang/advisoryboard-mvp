import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ZoomMeetingRule(Base):
    """
    Zoom-specific routing rule: maps meeting attributes to clients.

    match_field values:
      - 'topic_contains'     — match_value appears in the meeting topic (case-insensitive)
      - 'participant_email'   — match_value is an email address of a participant
      - 'meeting_id_prefix'   — meeting ID starts with match_value
    """

    __tablename__ = "zoom_meeting_rules"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "match_value", "match_field",
            name="uq_zoom_meeting_rules_user_value_field",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    match_field: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    match_value: Mapped[str] = mapped_column(
        String(500), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    client: Mapped["Client"] = relationship("Client")
