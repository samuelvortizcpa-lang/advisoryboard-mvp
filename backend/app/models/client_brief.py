import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.client import Client


class ClientBrief(Base):
    """
    A generated meeting-prep brief for a client.

    Created on demand by the brief generator service using GPT-4o.
    Contains a markdown summary of the client's documents, action items,
    and key financial details.
    """

    __tablename__ = "client_briefs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Clerk user ID who generated the brief
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Markdown content of the generated brief
    content: Mapped[str] = mapped_column(Text, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action_item_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Flexible metadata (e.g. model used, generation time, token count)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata_",
        JSONB,
        nullable=True,
    )

    # -----------------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------------

    client: Mapped["Client"] = relationship(
        "Client",
        back_populates="briefs",
    )

    def __repr__(self) -> str:
        return (
            f"<ClientBrief id={self.id} client_id={self.client_id} "
            f"generated_at={self.generated_at}>"
        )
