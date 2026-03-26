"""
Version comparison result schemas.
Covers config diff (field-level), adapter version diff (endpoint-level),
and promotion/rollback decision records.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from .common import (
    NonEmptyStr,
    OrchestratorBase,
    ResourceId,
    SemVer,
    TenantId,
    TimestampedMixin,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChangeType(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    REORDERED = "reordered"
    UNCHANGED = "unchanged"


class CompatibilityLevel(StrEnum):
    COMPATIBLE = "compatible"           # safe to upgrade; no consumer changes needed
    BACKWARD_COMPATIBLE = "backward_compatible"  # old consumers still work
    BREAKING = "breaking"               # requires consumer changes
    UNKNOWN = "unknown"


class PromotionDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    AUTO_APPROVED = "auto_approved"


# ---------------------------------------------------------------------------
# Field-level diff
# ---------------------------------------------------------------------------

class FieldChange(OrchestratorBase):
    path: NonEmptyStr       # dot-notation path to changed field
    change_type: ChangeType
    before: Any | None = None
    after: Any | None = None
    breaking: bool = False
    note: str | None = None


# ---------------------------------------------------------------------------
# Endpoint-level diff (adapter version comparison)
# ---------------------------------------------------------------------------

class EndpointChange(OrchestratorBase):
    endpoint_id: str
    method: str | None
    path: str | None
    change_type: ChangeType
    field_changes: list[FieldChange] = Field(default_factory=list)
    breaking: bool = False
    breaking_reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema diff (JSON Schema structural comparison)
# ---------------------------------------------------------------------------

class SchemaDiffEntry(OrchestratorBase):
    schema_name: NonEmptyStr
    change_type: ChangeType
    field_changes: list[FieldChange] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration version diff
# ---------------------------------------------------------------------------

class ConfigVersionDiffRequest(OrchestratorBase):
    tenant_id: TenantId
    configuration_id: ResourceId
    from_version: int = Field(..., ge=1)
    to_version: int = Field(..., ge=1)

    @model_validator(mode="after")
    def versions_differ(self) -> "ConfigVersionDiffRequest":
        if self.from_version == self.to_version:
            raise ValueError("from_version and to_version must differ.")
        return self


class ConfigVersionDiff(OrchestratorBase):
    configuration_id: ResourceId
    from_version: int
    to_version: int
    from_created_at: str
    to_created_at: str
    field_mapping_changes: list[FieldChange] = Field(default_factory=list)
    hook_changes: list[FieldChange] = Field(default_factory=list)
    policy_changes: list[FieldChange] = Field(default_factory=list)
    total_changes: int = 0
    breaking_changes: list[str] = Field(default_factory=list)
    has_breaking_changes: bool = False
    summary: str | None = None

    @model_validator(mode="after")
    def derive_totals(self) -> "ConfigVersionDiff":
        all_changes = (
            self.field_mapping_changes
            + self.hook_changes
            + self.policy_changes
        )
        object.__setattr__(self, "total_changes", len(all_changes))
        breaking = [c for c in all_changes if c.breaking]
        object.__setattr__(
            self,
            "breaking_changes",
            [c.note or c.path for c in breaking],
        )
        object.__setattr__(self, "has_breaking_changes", len(breaking) > 0)
        return self


# ---------------------------------------------------------------------------
# Adapter version diff
# ---------------------------------------------------------------------------

class AdapterVersionDiffRequest(OrchestratorBase):
    adapter_id: ResourceId
    from_version: SemVer
    to_version: SemVer

    @model_validator(mode="after")
    def versions_differ(self) -> "AdapterVersionDiffRequest":
        if self.from_version == self.to_version:
            raise ValueError("from_version and to_version must be different semver strings.")
        return self


class AdapterVersionDiff(OrchestratorBase):
    adapter_id: ResourceId
    from_version: SemVer
    to_version: SemVer
    compatibility: CompatibilityLevel
    endpoint_changes: list[EndpointChange] = Field(default_factory=list)
    schema_changes: list[SchemaDiffEntry] = Field(default_factory=list)
    auth_scheme_changed: bool = False
    base_url_changed: bool = False
    breaking_changes: list[str] = Field(default_factory=list)
    migration_guide: str | None = None
    auto_migration_possible: bool = False
    affected_configurations: list[ResourceId] = Field(default_factory=list)
    # adapter's own declared breaking_changes from AdapterVersionCreate
    declared_breaking_changes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_compatibility(self) -> "AdapterVersionDiff":
        has_breaking = (
            bool(self.breaking_changes)
            or any(e.breaking for e in self.endpoint_changes)
            or self.auth_scheme_changed
        )
        if has_breaking and self.compatibility == CompatibilityLevel.COMPATIBLE:
            object.__setattr__(self, "compatibility", CompatibilityLevel.BREAKING)
        return self


# ---------------------------------------------------------------------------
# Promotion record
# ---------------------------------------------------------------------------

class PromotionRequest(OrchestratorBase):
    tenant_id: TenantId
    configuration_id: ResourceId
    from_version: int
    to_version: int
    justification: str | None = Field(default=None, max_length=2000)
    test_run_id: ResourceId | None = None  # must be PASSED for auto-approval
    skip_test_requirement: bool = False     # requires ENTERPRISE + admin role


class PromotionRecord(TimestampedMixin):
    id: ResourceId
    tenant_id: TenantId
    configuration_id: ResourceId
    from_version: int
    to_version: int
    decision: PromotionDecision
    decided_by: str | None = None  # actor ID; None = auto
    justification: str | None
    test_run_id: ResourceId | None
    diff_summary: ConfigVersionDiff | None = None
    rolled_back_at: str | None = None
    rollback_reason: str | None = None


# ---------------------------------------------------------------------------
# Rollback request
# ---------------------------------------------------------------------------

class RollbackRequest(OrchestratorBase):
    tenant_id: TenantId
    configuration_id: ResourceId
    target_version: int = Field(..., ge=1)
    reason: NonEmptyStr = Field(..., max_length=1000)
    dry_run: bool = False  # preview impact without actually applying
