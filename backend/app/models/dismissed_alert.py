import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DismissedAlert(Base):
    """
    Tracks which alerts a user has dismissed so they are not shown again.

    The unique constraint on (user_id, alert_type, related_id) ensures
    a user can only dismiss a specific alert once.
    """

    __tablename__ = "dismissed_alerts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "alert_type", "related_id",
            name="uq_dismissed_alerts_user_type_related",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Clerk user ID
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Alert type: 'overdue_action', 'upcoming_deadline', 'stale_client', 'stuck_document'
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # The ID of the related entity (action item, client, or document)
    related_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<DismissedAlert id={self.id} user_id={self.user_id!r} "
            f"alert_type={self.alert_type!r} related_id={self.related_id}>"
        )
