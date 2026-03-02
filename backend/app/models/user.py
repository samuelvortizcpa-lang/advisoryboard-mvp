import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.document import Document
    from app.models.interaction import Interaction


class User(Base):
    """
    Mirrors a Clerk user in the local database.

    Created automatically on first authenticated request so that foreign keys
    from other tables can reference a real row.  The clerk_id is the canonical
    identifier; the rest of the fields are cached from the Clerk JWT payload.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    clerk_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

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

    clients: Mapped[List["Client"]] = relationship(
        "Client",
        back_populates="owner",
        foreign_keys="Client.owner_id",
        cascade="all, delete-orphan",
    )
    documents_uploaded: Mapped[List["Document"]] = relationship(
        "Document",
        back_populates="uploader",
        foreign_keys="Document.uploaded_by",
    )
    interactions_created: Mapped[List["Interaction"]] = relationship(
        "Interaction",
        back_populates="creator",
        foreign_keys="Interaction.created_by",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} clerk_id={self.clerk_id!r} email={self.email!r}>"
