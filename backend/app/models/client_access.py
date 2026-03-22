import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client


class ClientAccess(Base):
    """
    Controls which org members can access a specific client.

    Used for fine-grained access within an organization — e.g. only
    certain team members should see a particular client's data.
    """

    __tablename__ = "client_access"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "user_id", name="uq_client_access_client_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Clerk user ID of the member who has access
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # 'full', 'readonly', 'none'
    access_level: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="full"
    )

    # Clerk user ID of who granted access
    assigned_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
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
        foreign_keys=[client_id],
    )

    def __repr__(self) -> str:
        return (
            f"<ClientAccess client_id={self.client_id} "
            f"user_id={self.user_id!r} level={self.access_level!r}>"
        )
