"""
Hook model.

Hooks are lifecycle callbacks attached to either an Adapter (system-level)
or a specific Integration (tenant-level override).  They fire at defined
points in the request pipeline.

lifecycle_event examples:
  pre_request, post_request, on_error, on_timeout,
  on_auth_refresh, pre_transform, post_transform

hook_type:
  webhook    — HTTP POST to an external URL
  script     — inline Python expression (sandboxed)
  lambda     — AWS Lambda / GCP Cloud Function ARN

handler_config JSONB stores type-specific payload:
  webhook:  { url, headers, retry_policy, timeout_ms }
  script:   { code, runtime, timeout_ms }
  lambda:   { arn, payload_template, invocation_type }
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, JSONBType, TimestampMixin, SoftDeleteMixin, uuid_pk

if TYPE_CHECKING:
    from app.db.models.adapter import Adapter
    from app.db.models.integration import Integration


class Hook(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "hooks"

    id: Mapped[str] = uuid_pk()
    # Hooks are scoped to either an adapter OR an integration, not both.
    # Exactly one of these must be non-null (enforced by CHECK constraint).
    adapter_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("adapters.id", ondelete="CASCADE"),
        nullable=True,
        comment="Set for adapter-level system hooks",
    )
    integration_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=True,
        comment="Set for tenant-level integration hooks",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle_event: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="pre_request | post_request | on_error | on_timeout | pre_transform | post_transform",
    )
    hook_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="webhook | script | lambda",
    )
    handler_config: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    # Execution order when multiple hooks match the same event
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        comment="Lower number = higher priority",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    adapter: Mapped["Adapter | None"] = relationship(
        "Adapter",
        back_populates="hooks",
        lazy="noload",
    )
    integration: Mapped["Integration | None"] = relationship(
        "Integration",
        back_populates="hooks",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_hooks_adapter_id", "adapter_id"),
        Index("ix_hooks_integration_id", "integration_id"),
        Index("ix_hooks_lifecycle_event", "lifecycle_event"),
        # Fast lookup: all enabled hooks for an integration + event
        Index(
            "ix_hooks_integration_event_enabled",
            "integration_id",
            "lifecycle_event",
            "is_enabled",
        ),
        CheckConstraint(
            "hook_type IN ('webhook','script','lambda')",
            name="ck_hooks_hook_type",
        ),
        CheckConstraint(
            "(adapter_id IS NOT NULL AND integration_id IS NULL) OR "
            "(adapter_id IS NULL AND integration_id IS NOT NULL)",
            name="ck_hooks_scope_xor",
        ),
    )

    def __repr__(self) -> str:
        scope = f"adapter={self.adapter_id}" if self.adapter_id else f"integration={self.integration_id}"
        return f"<Hook id={self.id} {scope} event={self.lifecycle_event}>"
