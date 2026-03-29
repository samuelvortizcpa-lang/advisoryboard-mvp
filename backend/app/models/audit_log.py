"""
Audit log model for compliance tracking.

Records who accessed what data, when, and from where. Critical for CPA firms
that must demonstrate data access controls to clients and regulators.

NOTE: A retention policy should be added later to archive logs older than 2 years.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_timestamp", "org_id", "timestamp"),
        Index("ix_audit_logs_user_timestamp", "user_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog {self.action} user={self.user_id!r} "
            f"resource={self.resource_type}/{self.resource_id}>"
        )
