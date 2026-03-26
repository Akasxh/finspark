"""
Audit log entry schemas.
Every mutation to any resource produces an immutable audit record.
Append-only — no update or delete endpoints exist for audit logs.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, IPvAnyAddress, field_validator

from .common import (
    NonEmptyStr,
    OrchestratorBase,
    ResourceId,
    TenantId,
    TimestampedMixin,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AuditAction(StrEnum):
    # Resources
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    # Auth
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    TOKEN_ISSUED = "token_issued"
    TOKEN_REVOKED = "token_revoked"
    # Configuration lifecycle
    CONFIG_ACTIVATE = "config_activate"
    CONFIG_ROLLBACK = "config_rollback"
    CONFIG_PROMOTE = "config_promote"
    # Integration runtime
    INTEGRATION_TRIGGERED = "integration_triggered"
    INTEGRATION_SUCCEEDED = "integration_succeeded"
    INTEGRATION_FAILED = "integration_failed"
    INTEGRATION_RETRIED = "integration_retried"
    # Test/simulation
    SIMULATION_STARTED = "simulation_started"
    SIMULATION_COMPLETED = "simulation_completed"
    SIMULATION_ABORTED = "simulation_aborted"
    # Credential operations
    CREDENTIAL_CREATED = "credential_created"
    CREDENTIAL_ROTATED = "credential_rotated"
    CREDENTIAL_ACCESSED = "credential_accessed"
    # Webhook
    WEBHOOK_CREATED = "webhook_created"
    WEBHOOK_FIRED = "webhook_fired"
    WEBHOOK_FAILED = "webhook_failed"
    # Compliance
    DATA_EXPORT = "data_export"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"


class AuditResourceType(StrEnum):
    TENANT = "tenant"
    ADAPTER = "adapter"
    ADAPTER_VERSION = "adapter_version"
    CONFIGURATION = "configuration"
    INTEGRATION = "integration"
    DOCUMENT = "document"
    WEBHOOK = "webhook"
    TEST_RESULT = "test_result"
    CREDENTIAL = "credential"
    USER = "user"
    API_KEY = "api_key"


class AuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Diff payload — records before/after state for mutations
# ---------------------------------------------------------------------------

class FieldDiff(OrchestratorBase):
    field_path: NonEmptyStr
    before: Any | None
    after: Any | None
    masked: bool = False  # True when the field is PII or credential


class ResourceDiff(OrchestratorBase):
    changes: list[FieldDiff] = Field(default_factory=list)
    fields_added: list[str] = Field(default_factory=list)
    fields_removed: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Actor — who performed the action
# ---------------------------------------------------------------------------

class ActorType(StrEnum):
    USER = "user"
    API_KEY = "api_key"
    SERVICE_ACCOUNT = "service_account"
    SYSTEM = "system"


class AuditActor(OrchestratorBase):
    actor_type: ActorType
    actor_id: str  # user UUID, API key ID, or service name
    email: str | None = None
    ip_address: str | None = None  # stored as string for immutability
    user_agent: str | None = None
    session_id: str | None = None


# ---------------------------------------------------------------------------
# Audit log entry
# ---------------------------------------------------------------------------

class AuditLogCreate(OrchestratorBase):
    """
    Written internally by the service layer — never exposed on inbound API.
    Included here for internal typing correctness.
    """
    tenant_id: TenantId
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: str  # string to accommodate non-UUID legacy IDs
    resource_name: str | None = None
    actor: AuditActor
    outcome: AuditOutcome
    severity: AuditSeverity = AuditSeverity.INFO
    diff: ResourceDiff | None = None
    request_id: str | None = None
    trace_id: str | None = None
    duration_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogRead(OrchestratorBase):
    id: ResourceId
    tenant_id: TenantId
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: str
    resource_name: str | None
    actor: AuditActor
    outcome: AuditOutcome
    severity: AuditSeverity
    diff: ResourceDiff | None
    request_id: str | None
    trace_id: str | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    metadata: dict[str, Any]
    created_at: str  # ISO-8601; audit records are immutable, no updated_at


class AuditLogListItem(OrchestratorBase):
    id: ResourceId
    tenant_id: TenantId
    action: AuditAction
    resource_type: AuditResourceType
    resource_id: str
    outcome: AuditOutcome
    severity: AuditSeverity
    actor_id: str
    created_at: str


# ---------------------------------------------------------------------------
# Query filters
# ---------------------------------------------------------------------------

class AuditLogQueryParams(OrchestratorBase):
    tenant_id: TenantId | None = None
    action: AuditAction | None = None
    resource_type: AuditResourceType | None = None
    resource_id: str | None = None
    actor_id: str | None = None
    outcome: AuditOutcome | None = None
    severity: AuditSeverity | None = None
    from_ts: str | None = None  # ISO-8601
    to_ts: str | None = None    # ISO-8601
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
