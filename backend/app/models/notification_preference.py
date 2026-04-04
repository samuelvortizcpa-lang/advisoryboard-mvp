import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationPreference(Base):
    """Per-user, per-org email notification preferences."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_notification_prefs_user_org"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    org_id: Mapped[str] = mapped_column(String(255), nullable=False)

    task_assigned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    task_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deadline_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deadline_reminder_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    daily_digest: Mapped[bool] = mapped_column(
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

    def __repr__(self) -> str:
        return f"<NotificationPreference user_id={self.user_id!r} org_id={self.org_id!r}>"
