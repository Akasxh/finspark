"""
AuditLog model.

Immutable audit trail.  Every state-changing operation on any entity
appends a row here.  Rows are NEVER updated or deleted (soft-delete
pattern does NOT apply here).

Design principles:
- Write-only from the application layer; queries are read-only.
- actor_id + actor_type support both human users and service accounts.
- before_state / after_state capture full JSONB snapshots, not diffs —
  this makes compliance queries self-contained without chasing FK chains.
- ip_address / user_agent included for security compliance (SOC2, PCI-DSS).
- Partition by created_at monthly in PostgreSQL for long-term retention
  without bloat (expressed as a comment; partition DDL goes in migration).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, JSONBType, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.db.models.tenant import Tenant
    from app.db.models.integration import Integration


class AuditLog(TimestampMixin, Base):
    """
    Append-only audit log.  No soft-delete, no updates.

    PostgreSQL production: declare as PARTITION BY RANGE (created_at)
    with monthly child tables and pg_partman for automated management.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = uuid_pk()
    # Tenant scoping — nullable only for system-level events (seed, admin ops)
    tenant_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Optional: link to the specific integration this event concerns
    integration_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("integrations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Who performed the action
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="user",
        comment="user | service | system | ai_agent",
    )
    # What happened
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="e.g. integration.created, config.updated, hook.fired, version.rollback",
    )
    entity_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="ORM model name: Integration, Configuration, Hook, etc.",
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="PK of the affected entity row",
    )
    # Full JSONB snapshots; null for create (no before) / delete (no after)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONBType(),
        nullable=True,
    )
    after_state: Mapped[dict[str, Any] | None] = mapped_column(
        JSONBType(),
        nullable=True,
    )
    # Request context for security compliance
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Correlation ID from the HTTP request",
    )
    # Additional structured metadata (tags, reason, change ticket, etc.)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="success",
        comment="success | failure | partial",
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant",
        back_populates="audit_logs",
        lazy="noload",
    )
    integration: Mapped["Integration | None"] = relationship(
        "Integration",
        back_populates="audit_logs",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_integration_id", "integration_id"),
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        # Compliance: "all config changes for tenant X in date range"
        Index(
            "ix_audit_logs_tenant_created",
            "tenant_id",
            "created_at",
        ),
        # Correlation ID lookups for distributed tracing
        Index("ix_audit_logs_request_id", "request_id"),
        CheckConstraint(
            "actor_type IN ('user','service','system','ai_agent')",
            name="ck_audit_logs_actor_type",
        ),
        CheckConstraint(
            "outcome IN ('success','failure','partial')",
            name="ck_audit_logs_outcome",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action} "
            f"entity={self.entity_type}:{self.entity_id}>"
        )
