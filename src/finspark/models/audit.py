"""Audit log model for tracking all changes."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from finspark.models.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Immutable audit log entry."""

    __tablename__ = "audit_logs"

    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # create, update, delete, deploy, rollback
    resource_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # configuration, adapter, simulation
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
