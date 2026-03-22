import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization


class OrganizationMember(Base):
    """
    Maps a Clerk user to an organization with a specific role.

    A user can belong to multiple organizations. The (org_id, user_id) pair
    is unique — one membership row per user per org.
    """

    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_org_members_org_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Clerk user ID
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # 'admin', 'member', 'readonly'
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="member"
    )

    # Who invited this member (Clerk user ID)
    invited_by: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    invited_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="members",
        foreign_keys=[org_id],
    )

    def __repr__(self) -> str:
        return (
            f"<OrganizationMember org_id={self.org_id} "
            f"user_id={self.user_id!r} role={self.role!r}>"
        )
