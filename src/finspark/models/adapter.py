"""Integration adapter models."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from finspark.models.base import Base, TimestampMixin, UUIDMixin


class Adapter(Base, UUIDMixin, TimestampMixin):
    """Pre-built integration adapter (e.g., CIBIL Bureau, Razorpay)."""

    __tablename__ = "adapters"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # bureau, kyc, payment, etc.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    versions: Mapped[list["AdapterVersion"]] = relationship(back_populates="adapter")


class AdapterVersion(Base, UUIDMixin, TimestampMixin):
    """Specific version of an adapter with its schema and config."""

    __tablename__ = "adapter_versions"

    adapter_id: Mapped[str] = mapped_column(ForeignKey("adapters.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g., "v1", "v2.1"
    version_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, deprecated, beta
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auth_type: Mapped[str] = mapped_column(
        String(50), default="api_key"
    )  # api_key, oauth2, certificate
    request_schema: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON Schema
    response_schema: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON Schema
    endpoints: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON - list of endpoints
    config_template: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON - default config
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)

    adapter: Mapped["Adapter"] = relationship(back_populates="versions")
