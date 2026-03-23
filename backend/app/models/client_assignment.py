import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client


class ClientAssignment(Base):
    """
    Tracks which org members are assigned to work on a specific client.

    Distinct from ClientAccess (which controls visibility/permissions) —
    assignments represent active work responsibility.
    """

    __tablename__ = "client_assignments"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "user_id", "org_id", name="uq_client_user_org"
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

    # Clerk user ID of the assigned member
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Clerk user ID of the admin who created the assignment
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Future: lead, reviewer, preparer
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="assigned"
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
            f"<ClientAssignment client_id={self.client_id} "
            f"user_id={self.user_id!r} role={self.role!r}>"
        )
