"""
Configuration and ConfigurationVersion models.

Configuration       — the live config record for an Integration.
ConfigurationVersion — append-only history table; every change to
                       Configuration.data creates a new version row.

Version history strategy:
- ConfigurationVersion is NEVER updated, only inserted.
- Configuration.current_version is a denormalized pointer to the active
  ConfigurationVersion.id for O(1) lookup without a MAX(version_num) scan.
- version_num is a monotonically increasing integer per (integration_id).
  Enforced via unique constraint; the application must increment it.
- diff_patch stores a JSON Patch (RFC 6902) for incremental audit review.

This design supports:
  * Rollback: set Configuration.current_version = older ConfigurationVersion.id
  * Diff: read diff_patch from any version row
  * Full history: SELECT * FROM configuration_versions WHERE integration_id=X ORDER BY version_num
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, JSONBType, SoftDeleteMixin, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.db.models.integration import Integration


class Configuration(TimestampMixin, SoftDeleteMixin, Base):
    """
    Live configuration for an Integration.

    `data` is the merged, resolved configuration blob sent to the adapter
    at runtime.  It is recomputed and snapshotted as a new
    ConfigurationVersion on every change.
    """

    __tablename__ = "configurations"

    id: Mapped[str] = uuid_pk()
    integration_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Points to the ConfigurationVersion that is currently active.
    # FK declared after ConfigurationVersion table is defined (see below).
    current_version_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("configuration_versions.id", ondelete="SET NULL", use_alter=True, name="fk_configs_current_version"),
        nullable=True,
    )
    # Denormalized latest version number for display/API responses
    current_version_num: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    # Source of this config: manual | ai_generated | imported | rollback
    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manual",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        comment="draft | active | archived",
    )

    # Relationships
    integration: Mapped["Integration"] = relationship(
        "Integration",
        back_populates="configurations",
        lazy="noload",
    )
    current_version: Mapped["ConfigurationVersion | None"] = relationship(
        "ConfigurationVersion",
        foreign_keys=[current_version_id],
        lazy="noload",
    )
    versions: Mapped[list["ConfigurationVersion"]] = relationship(
        "ConfigurationVersion",
        foreign_keys="ConfigurationVersion.configuration_id",
        back_populates="configuration",
        lazy="noload",
        order_by="ConfigurationVersion.version_num.desc()",
    )

    __table_args__ = (
        # One active config per integration (can be relaxed for drafts)
        UniqueConstraint(
            "integration_id",
            "status",
            name="uq_configurations_integration_active",
            # PostgreSQL: add postgresql_where="status='active'" in migration
        ),
        Index("ix_configurations_integration_id", "integration_id"),
        Index("ix_configurations_status", "status"),
        CheckConstraint(
            "source IN ('manual','ai_generated','imported','rollback')",
            name="ck_configurations_source",
        ),
        CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_configurations_status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Configuration id={self.id} integration={self.integration_id} "
            f"v={self.current_version_num}>"
        )


class ConfigurationVersion(TimestampMixin, Base):
    """
    Immutable version snapshot — append-only.

    Never UPDATE this table.  Every config change = new row.
    """

    __tablename__ = "configuration_versions"

    id: Mapped[str] = uuid_pk()
    configuration_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("configurations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized for direct JOIN from integrations table
    integration_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_num: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monotonically increasing per configuration_id",
    )
    # Full resolved config data at this point in time
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONBType(),
        nullable=False,
        default=dict,
    )
    # RFC 6902 JSON Patch from previous version; null for v1
    diff_patch: Mapped[dict[str, Any] | None] = mapped_column(
        JSONBType(),
        nullable=True,
        comment="JSON Patch (RFC 6902) from previous version",
    )
    # Who/what created this version
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How was this version created
    change_source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manual",
        comment="manual | ai_generated | imported | rollback",
    )

    # Relationships
    configuration: Mapped["Configuration"] = relationship(
        "Configuration",
        foreign_keys=[configuration_id],
        back_populates="versions",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint(
            "configuration_id",
            "version_num",
            name="uq_config_versions_config_version_num",
        ),
        Index("ix_config_versions_configuration_id", "configuration_id"),
        Index("ix_config_versions_integration_id", "integration_id"),
        # Fast "give me the latest N versions for this integration"
        Index(
            "ix_config_versions_integration_version",
            "integration_id",
            "version_num",
        ),
        CheckConstraint(
            "change_source IN ('manual','ai_generated','imported','rollback')",
            name="ck_config_versions_change_source",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ConfigurationVersion config={self.configuration_id} "
            f"v={self.version_num}>"
        )
