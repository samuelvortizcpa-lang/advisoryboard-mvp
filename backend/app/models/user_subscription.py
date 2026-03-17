import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserSubscription(Base):
    """
    Tracks a user's subscription tier and strategic query usage quota.

    One row per user. Billing period resets monthly.
    """

    __tablename__ = "user_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )

    tier: Mapped[str] = mapped_column(
        String(50), nullable=False, default="starter"
    )

    strategic_queries_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    strategic_queries_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    billing_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    billing_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Stripe integration
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    stripe_status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, default="none"
    )
    payment_status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<UserSubscription user_id={self.user_id!r} tier={self.tier!r} "
            f"used={self.strategic_queries_used}/{self.strategic_queries_limit}>"
        )
