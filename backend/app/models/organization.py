import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization_member import OrganizationMember


class Organization(Base):
    """
    A tenant organization — either a personal workspace or a multi-member firm.

    Every user gets a personal org on sign-up. Firm orgs can have multiple
    members with role-based access.
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )

    # Clerk organization ID — null for auto-created personal orgs
    clerk_org_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # Clerk user ID of the org creator/owner
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # 'personal' or 'firm'
    org_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="personal"
    )

    # Seat limit based on subscription tier
    max_members: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )

    # Future: org-level preferences
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
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

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    members: Mapped[List["OrganizationMember"]] = relationship(
        "OrganizationMember",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Organization id={self.id} name={self.name!r} "
            f"type={self.org_type!r}>"
        )
