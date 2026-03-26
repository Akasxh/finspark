"""
FieldMapping model.

Maps source fields (from the tenant's internal data model) to target
fields (the adapter's input_schema).  Supports:

  - direct     : source_path → target_path, optional static default
  - transform  : same + a transform_expr (JSONata / jmespath expression)
  - computed   : no source_path, value fully derived from transform_expr
  - constant   : no source_path, constant value from default_value

transform_expr is evaluated by the Auto-Configuration Engine at runtime.
Expressions are stored verbatim; the engine validates them against
AdapterVersion.input_schema before activation.
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, JSONBType, TimestampMixin, SoftDeleteMixin, uuid_pk

if TYPE_CHECKING:
    from app.db.models.integration import Integration


class FieldMapping(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "field_mappings"

    id: Mapped[str] = uuid_pk()
    integration_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human label for this mapping rule",
    )
    mapping_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="direct",
        comment="direct | transform | computed | constant",
    )
    # JSONPath / dot-notation path in source document
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # JSONPath / dot-notation path in adapter input schema
    target_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # JSONata / jmespath expression; null for direct mappings
    transform_expr: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Static fallback / constant value
    default_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSONBType(),
        nullable=True,
        comment="Static value; stored as JSONB to handle any scalar/object type",
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Execution order when multiple mappings target the same field
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI-generated confidence score [0.0, 1.0]; null for manually created
    ai_confidence: Mapped[float | None] = mapped_column(nullable=True)
    # Serialized reasoning from the AI engine for this mapping suggestion
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship
    integration: Mapped["Integration"] = relationship(
        "Integration",
        back_populates="field_mappings",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint(
            "integration_id",
            "target_path",
            name="uq_field_mappings_integration_target",
        ),
        Index("ix_field_mappings_integration_id", "integration_id"),
        Index("ix_field_mappings_target_path", "target_path"),
        Index(
            "ix_field_mappings_integration_enabled",
            "integration_id",
            "is_enabled",
        ),
        CheckConstraint(
            "mapping_type IN ('direct','transform','computed','constant')",
            name="ck_field_mappings_mapping_type",
        ),
        CheckConstraint(
            "ai_confidence IS NULL OR (ai_confidence >= 0.0 AND ai_confidence <= 1.0)",
            name="ck_field_mappings_ai_confidence_range",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FieldMapping id={self.id} integration={self.integration_id} "
            f"{self.source_path} → {self.target_path}>"
        )
