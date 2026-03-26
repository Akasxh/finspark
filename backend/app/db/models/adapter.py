"""
Adapter and AdapterVersion models.

Adapter         — catalogue entry for an integration type (CIBIL, GSTN, Razorpay…)
AdapterVersion  — an immutable snapshot of an adapter's interface contract at
                  a given semver.  Multiple versions coexist; integrations pin
                  to a specific version.

Design:
- AdapterVersion rows are IMMUTABLE after publish (status → "published").
  Never UPDATE a published version; always INSERT a new one.
- input_schema / output_schema are JSON Schema drafts stored in JSONB,
  used by the Auto-Configuration Engine for field-mapping validation.
- default_config is the baseline JSONB config template cloned when an
  Integration is first created.
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
    from app.db.models.integration import Integration
    from app.db.models.hook import Hook


class Adapter(TimestampMixin, SoftDeleteMixin, Base):
    """
    Canonical registry entry for an external service adapter.

    Examples: CIBIL, Experian, GSTN, Razorpay, Perfios, NPCI-UPI.
    """

    __tablename__ = "adapters"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="machine-readable identifier: cibil, gstn, razorpay",
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="bureau | kyc | payment | fraud | open_banking | gst | other",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Provider-level docs URL, support contacts, SLA info
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationships
    versions: Mapped[list["AdapterVersion"]] = relationship(
        "AdapterVersion",
        back_populates="adapter",
        lazy="noload",
        order_by="AdapterVersion.created_at.desc()",
    )
    hooks: Mapped[list["Hook"]] = relationship(
        "Hook",
        back_populates="adapter",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_adapters_slug"),
        Index("ix_adapters_category", "category"),
        Index("ix_adapters_slug", "slug"),
        CheckConstraint(
            "category IN ('bureau','kyc','payment','fraud','open_banking','gst','other')",
            name="ck_adapters_category",
        ),
    )

    def __repr__(self) -> str:
        return f"<Adapter id={self.id} slug={self.slug}>"


class AdapterVersion(TimestampMixin, Base):
    """
    Immutable versioned snapshot of an Adapter's interface contract.

    status lifecycle: draft → published → deprecated → retired
    Once published, this row must not be mutated.
    """

    __tablename__ = "adapter_versions"

    id: Mapped[str] = uuid_pk()
    adapter_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("adapters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    semver: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="semver string: 1.0.0, 2.3.1-beta",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        comment="draft | published | deprecated | retired",
    )
    # Full JSON Schema for inbound request fields
    input_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    # Full JSON Schema for outbound response fields
    output_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    # Baseline config cloned for new Integrations
    default_config: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    # Breaking-change flag: if True, auto-migration is blocked
    is_breaking: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
    )
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    adapter: Mapped["Adapter"] = relationship(
        "Adapter",
        back_populates="versions",
        lazy="noload",
    )
    integrations: Mapped[list["Integration"]] = relationship(
        "Integration",
        back_populates="adapter_version",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint("adapter_id", "semver", name="uq_adapter_versions_adapter_semver"),
        Index("ix_adapter_versions_adapter_id", "adapter_id"),
        Index("ix_adapter_versions_status", "status"),
        # Composite: common query pattern — find published versions for an adapter
        Index("ix_adapter_versions_adapter_status", "adapter_id", "status"),
        CheckConstraint(
            "status IN ('draft','published','deprecated','retired')",
            name="ck_adapter_versions_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<AdapterVersion adapter={self.adapter_id} semver={self.semver} status={self.status}>"
