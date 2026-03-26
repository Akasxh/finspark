"""
Tenant model.

A tenant maps 1:1 to a lending-platform customer.  All other entities
carry a tenant_id FK so every query is implicitly scoped.

settings JSONB: arbitrary tenant-level overrides (rate limits, feature
flags, branding) without schema migrations.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, JSONBType, SoftDeleteMixin, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.db.models.integration import Integration
    from app.db.models.audit_log import AuditLog


class Tenant(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    plan: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="standard",
        comment="standard | enterprise | trial",
    )
    # Flexible tenant-level overrides: rate limits, feature flags, etc.
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    # Vault key reference — the actual secret lives in HashiCorp Vault / AWS SM.
    # We only store the key ID, never the secret itself.
    vault_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    integrations: Mapped[list["Integration"]] = relationship(
        "Integration",
        back_populates="tenant",
        lazy="noload",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="tenant",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        Index("ix_tenants_slug", "slug"),
        Index("ix_tenants_is_deleted", "is_deleted"),
        # PostgreSQL partial index equivalent expressed generically;
        # the migration can specialise it with postgresql_where.
        Index("ix_tenants_active_slug", "slug", "is_deleted"),
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} slug={self.slug}>"
