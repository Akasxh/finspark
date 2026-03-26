"""
Tenant model with full isolation semantics.
Every resource in the system has a tenant_id FK; these schemas enforce
that boundary at the API layer.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import EmailStr, Field, HttpUrl, field_validator, model_validator

from .common import (
    NonEmptyStr,
    OrchestratorBase,
    ResourceId,
    SlugStr,
    TenantId,
    TimestampedMixin,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TenantTier(StrEnum):
    SANDBOX = "sandbox"
    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"


class TenantStatus(StrEnum):
    PENDING_SETUP = "pending_setup"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OFFBOARDED = "offboarded"


class DataResidencyRegion(StrEnum):
    IN_SOUTH = "in-south"
    IN_WEST = "in-west"
    EU_WEST = "eu-west"
    US_EAST = "us-east"
    AP_SOUTHEAST = "ap-southeast"


# ---------------------------------------------------------------------------
# Feature flags & quota
# ---------------------------------------------------------------------------

class TenantQuota(OrchestratorBase):
    max_adapters: int = Field(default=10, ge=1)
    max_configurations: int = Field(default=50, ge=1)
    max_api_calls_per_day: int = Field(default=10_000, ge=1)
    max_document_uploads_per_month: int = Field(default=100, ge=1)
    max_webhooks: int = Field(default=20, ge=1)
    max_test_runs_per_day: int = Field(default=500, ge=1)
    max_storage_gb: float = Field(default=5.0, gt=0.0)

    @staticmethod
    def for_tier(tier: TenantTier) -> "TenantQuota":
        presets: dict[TenantTier, dict[str, Any]] = {
            TenantTier.SANDBOX: dict(
                max_adapters=3,
                max_configurations=10,
                max_api_calls_per_day=1_000,
                max_document_uploads_per_month=10,
                max_webhooks=5,
                max_test_runs_per_day=50,
                max_storage_gb=0.5,
            ),
            TenantTier.STARTER: dict(
                max_adapters=10,
                max_configurations=50,
                max_api_calls_per_day=10_000,
                max_document_uploads_per_month=100,
                max_webhooks=20,
                max_test_runs_per_day=500,
                max_storage_gb=5.0,
            ),
            TenantTier.GROWTH: dict(
                max_adapters=50,
                max_configurations=500,
                max_api_calls_per_day=100_000,
                max_document_uploads_per_month=1_000,
                max_webhooks=100,
                max_test_runs_per_day=5_000,
                max_storage_gb=50.0,
            ),
            TenantTier.ENTERPRISE: dict(
                max_adapters=1_000,
                max_configurations=10_000,
                max_api_calls_per_day=10_000_000,
                max_document_uploads_per_month=100_000,
                max_webhooks=1_000,
                max_test_runs_per_day=100_000,
                max_storage_gb=1_000.0,
            ),
        }
        return TenantQuota(**presets[tier])


class TenantFeatureFlags(OrchestratorBase):
    ai_auto_config: bool = True
    simulation_engine: bool = True
    webhook_delivery: bool = True
    multi_version_parallel_test: bool = False  # only growth+
    custom_adapters: bool = False              # only growth+
    advanced_audit: bool = False               # only enterprise
    ip_allowlist: bool = False                 # only enterprise
    sso_saml: bool = False                     # only enterprise


# ---------------------------------------------------------------------------
# Contact / billing
# ---------------------------------------------------------------------------

class TenantContact(OrchestratorBase):
    name: NonEmptyStr
    email: EmailStr
    phone: str | None = Field(
        default=None,
        pattern=r"^\+?[1-9]\d{6,14}$",
    )
    role: str | None = None  # e.g. "Technical Lead", "Billing Contact"


# ---------------------------------------------------------------------------
# Network security
# ---------------------------------------------------------------------------

class IpAllowlistEntry(OrchestratorBase):
    cidr: str = Field(..., description="IPv4/IPv6 CIDR block")
    label: str | None = None

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        import ipaddress
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid CIDR '{v}': {exc}") from exc
        return v


# ---------------------------------------------------------------------------
# Tenant CRUD
# ---------------------------------------------------------------------------

class TenantCreate(OrchestratorBase):
    slug: SlugStr
    name: NonEmptyStr = Field(..., max_length=200)
    tier: TenantTier = TenantTier.STARTER
    data_residency: DataResidencyRegion = DataResidencyRegion.IN_SOUTH
    primary_contact: TenantContact
    billing_contact: TenantContact | None = None
    ip_allowlist: list[IpAllowlistEntry] = Field(default_factory=list, max_length=50)
    custom_quota: TenantQuota | None = None
    feature_flags: TenantFeatureFlags | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def apply_tier_defaults(self) -> "TenantCreate":
        if self.custom_quota is None:
            object.__setattr__(self, "custom_quota", TenantQuota.for_tier(self.tier))
        if self.feature_flags is None:
            flags = TenantFeatureFlags()
            # unlock tier-gated flags
            if self.tier in (TenantTier.GROWTH, TenantTier.ENTERPRISE):
                object.__setattr__(flags, "multi_version_parallel_test", True)
                object.__setattr__(flags, "custom_adapters", True)
            if self.tier == TenantTier.ENTERPRISE:
                object.__setattr__(flags, "advanced_audit", True)
                object.__setattr__(flags, "ip_allowlist", True)
                object.__setattr__(flags, "sso_saml", True)
            object.__setattr__(self, "feature_flags", flags)
        return self


class TenantUpdate(OrchestratorBase):
    name: str | None = Field(default=None, max_length=200)
    primary_contact: TenantContact | None = None
    billing_contact: TenantContact | None = None
    ip_allowlist: list[IpAllowlistEntry] | None = None
    custom_quota: TenantQuota | None = None
    feature_flags: TenantFeatureFlags | None = None
    metadata: dict[str, Any] | None = None
    status: TenantStatus | None = None


class TenantRead(TimestampedMixin):
    id: TenantId
    slug: SlugStr
    name: NonEmptyStr
    tier: TenantTier
    status: TenantStatus
    data_residency: DataResidencyRegion
    primary_contact: TenantContact
    billing_contact: TenantContact | None
    ip_allowlist: list[IpAllowlistEntry]
    quota: TenantQuota
    feature_flags: TenantFeatureFlags
    metadata: dict[str, Any]


class TenantListItem(OrchestratorBase):
    id: TenantId
    slug: SlugStr
    name: NonEmptyStr
    tier: TenantTier
    status: TenantStatus
    data_residency: DataResidencyRegion
    created_at: str


# ---------------------------------------------------------------------------
# Credential reference (no plaintext secrets in API layer)
# ---------------------------------------------------------------------------

class CredentialRef(OrchestratorBase):
    """
    All secrets live in Vault. The API layer only ever handles references.
    Actual secret values are written via the Vault API directly.
    """
    vault_path: NonEmptyStr
    key: NonEmptyStr
    version: int | None = None  # Vault KV v2 version pin; None = latest


class TenantAdapterCredentials(OrchestratorBase):
    tenant_id: TenantId
    adapter_id: ResourceId
    credential_refs: dict[str, CredentialRef]  # {field_name: vault_ref}
    rotate_at: str | None = None  # ISO-8601 — drives automated rotation
