"""
Integration model.

An Integration is a tenant's activated instance of a specific
AdapterVersion.  One tenant can have multiple integrations of the same
adapter (e.g., CIBIL v1 for legacy flows, CIBIL v2 for new origination).

status lifecycle: provisioning → active → paused → decommissioned
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, JSONBType, SoftDeleteMixin, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.db.models.tenant import Tenant
    from app.db.models.adapter import AdapterVersion
    from app.db.models.configuration import Configuration
    from app.db.models.hook import Hook
    from app.db.models.mapping import FieldMapping
    from app.db.models.test_result import TestResult
    from app.db.models.audit_log import AuditLog


class Integration(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "integrations"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    adapter_version_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("adapter_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human label: 'CIBIL Production', 'Razorpay UAT'",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="provisioning",
        comment="provisioning | active | paused | decommissioned",
    )
    environment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="sandbox",
        comment="sandbox | uat | production",
    )
    # Runtime overrides at integration level (endpoint URL, timeouts, etc.)
    # These merge with AdapterVersion.default_config at resolution time.
    runtime_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        back_populates="integrations",
        lazy="noload",
    )
    adapter_version: Mapped["AdapterVersion"] = relationship(
        "AdapterVersion",
        back_populates="integrations",
        lazy="noload",
    )
    configurations: Mapped[list["Configuration"]] = relationship(
        "Configuration",
        back_populates="integration",
        lazy="noload",
    )
    hooks: Mapped[list["Hook"]] = relationship(
        "Hook",
        back_populates="integration",
        lazy="noload",
    )
    field_mappings: Mapped[list["FieldMapping"]] = relationship(
        "FieldMapping",
        back_populates="integration",
        lazy="noload",
    )
    test_results: Mapped[list["TestResult"]] = relationship(
        "TestResult",
        back_populates="integration",
        lazy="noload",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="integration",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_integrations_tenant_id", "tenant_id"),
        Index("ix_integrations_adapter_version_id", "adapter_version_id"),
        Index("ix_integrations_status", "status"),
        # Most common query: list active integrations for a tenant
        Index("ix_integrations_tenant_status", "tenant_id", "status", "is_deleted"),
        Index("ix_integrations_tenant_env", "tenant_id", "environment"),
        CheckConstraint(
            "status IN ('provisioning','active','paused','decommissioned')",
            name="ck_integrations_status",
        ),
        CheckConstraint(
            "environment IN ('sandbox','uat','production')",
            name="ck_integrations_environment",
        ),
    )

    def __repr__(self) -> str:
        return f"<Integration id={self.id} tenant={self.tenant_id} status={self.status}>"
