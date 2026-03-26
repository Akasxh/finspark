"""Webhook models for integration event delivery."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finspark.models.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Webhook(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Registered webhook endpoint for receiving integration events."""

    __tablename__ = "webhooks"

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(512), nullable=False)  # Fernet-encrypted
    events: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="webhook", cascade="all, delete-orphan"
    )


class WebhookDelivery(Base, UUIDMixin, TimestampMixin):
    """Record of a webhook delivery attempt."""

    __tablename__ = "webhook_deliveries"

    webhook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    webhook: Mapped["Webhook"] = relationship(back_populates="deliveries")
