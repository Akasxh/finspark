"""
Configuration template schemas: field mappings, transformations, hooks.
A Configuration belongs to a tenant-adapter-version triplet and drives
how the Auto-Configuration Engine wires up an integration.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

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

class TransformationType(StrEnum):
    PASSTHROUGH = "passthrough"
    RENAME = "rename"
    TYPE_CAST = "type_cast"
    FORMAT_DATE = "format_date"
    REGEX_EXTRACT = "regex_extract"
    JMESPATH = "jmespath"
    JINJA2 = "jinja2"
    PYTHON_EXPR = "python_expr"   # sandboxed eval, restricted builtins
    CUSTOM_FUNCTION = "custom_function"
    CONSTANT = "constant"
    LOOKUP_TABLE = "lookup_table"


class HookEvent(StrEnum):
    PRE_REQUEST = "pre_request"
    POST_RESPONSE = "post_response"
    ON_ERROR = "on_error"
    ON_RETRY = "on_retry"
    ON_TIMEOUT = "on_timeout"
    ON_AUTH_REFRESH = "on_auth_refresh"
    PRE_TRANSFORM = "pre_transform"
    POST_TRANSFORM = "post_transform"


class HookRuntime(StrEnum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    WASM = "wasm"
    HTTP_CALLBACK = "http_callback"


class ConfigurationStatus(StrEnum):
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class RetryStrategy(StrEnum):
    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


# ---------------------------------------------------------------------------
# Transformation — discriminated union on `type`
# ---------------------------------------------------------------------------

class PassthroughTransform(OrchestratorBase):
    type: Literal[TransformationType.PASSTHROUGH] = TransformationType.PASSTHROUGH


class RenameTransform(OrchestratorBase):
    type: Literal[TransformationType.RENAME] = TransformationType.RENAME
    target_name: NonEmptyStr


class TypeCastTransform(OrchestratorBase):
    type: Literal[TransformationType.TYPE_CAST] = TransformationType.TYPE_CAST
    to_type: Literal["string", "integer", "float", "boolean", "date", "datetime"]
    date_format: str | None = None  # only for date/datetime


class FormatDateTransform(OrchestratorBase):
    type: Literal[TransformationType.FORMAT_DATE] = TransformationType.FORMAT_DATE
    input_format: str  # strptime pattern
    output_format: str  # strftime pattern


class RegexExtractTransform(OrchestratorBase):
    type: Literal[TransformationType.REGEX_EXTRACT] = TransformationType.REGEX_EXTRACT
    pattern: NonEmptyStr
    group: int = 0  # regex match group index
    fallback: str | None = None


class JmesPathTransform(OrchestratorBase):
    type: Literal[TransformationType.JMESPATH] = TransformationType.JMESPATH
    expression: NonEmptyStr  # JMESPath expression applied to the source document


class Jinja2Transform(OrchestratorBase):
    type: Literal[TransformationType.JINJA2] = TransformationType.JINJA2
    template: NonEmptyStr  # Jinja2 template string; `value` and `record` are in scope
    safe_mode: bool = True  # restricts dangerous filters


class PythonExprTransform(OrchestratorBase):
    type: Literal[TransformationType.PYTHON_EXPR] = TransformationType.PYTHON_EXPR
    expression: NonEmptyStr  # single expression; `value` bound to source field value
    # Allowed builtins subset; enforcement is in the execution sandbox
    allowed_builtins: list[str] = Field(
        default_factory=lambda: ["str", "int", "float", "bool", "len", "round"]
    )


class ConstantTransform(OrchestratorBase):
    type: Literal[TransformationType.CONSTANT] = TransformationType.CONSTANT
    value: Any


class LookupTableTransform(OrchestratorBase):
    type: Literal[TransformationType.LOOKUP_TABLE] = TransformationType.LOOKUP_TABLE
    table: dict[str, Any]  # {source_value: target_value}
    fallback: Any | None = None


class CustomFunctionTransform(OrchestratorBase):
    type: Literal[TransformationType.CUSTOM_FUNCTION] = TransformationType.CUSTOM_FUNCTION
    function_ref: NonEmptyStr  # dotted import path, e.g. "app.transforms.cibil.normalize_score"
    kwargs: dict[str, Any] = Field(default_factory=dict)


Transformation = (
    PassthroughTransform
    | RenameTransform
    | TypeCastTransform
    | FormatDateTransform
    | RegexExtractTransform
    | JmesPathTransform
    | Jinja2Transform
    | PythonExprTransform
    | ConstantTransform
    | LookupTableTransform
    | CustomFunctionTransform
)


# ---------------------------------------------------------------------------
# Field mapping
# ---------------------------------------------------------------------------

class FieldMapping(OrchestratorBase):
    mapping_id: str = Field(
        default_factory=lambda: str(__import__("uuid").uuid4())
    )
    source_path: NonEmptyStr   # dot-notation JSON path in source payload
    target_path: NonEmptyStr   # dot-notation JSON path in target payload
    required: bool = True
    nullable: bool = False
    transformations: list[Transformation] = Field(default_factory=list)
    description: str | None = None
    pii: bool = False  # flag for data classification — affects audit masking

    @model_validator(mode="after")
    def source_and_target_differ(self) -> "FieldMapping":
        # Not enforced as a hard rule since rename transforms handle it,
        # but useful for passthrough validation.
        return self


# ---------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------

class HttpCallbackHook(OrchestratorBase):
    runtime: Literal[HookRuntime.HTTP_CALLBACK] = HookRuntime.HTTP_CALLBACK
    url: str  # HttpUrl as str for flexibility (supports vault-interpolated URIs)
    method: str = Field(default="POST", pattern=r"^(GET|POST|PUT|PATCH)$")
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    retry_on_failure: bool = False


class PythonHook(OrchestratorBase):
    runtime: Literal[HookRuntime.PYTHON] = HookRuntime.PYTHON
    module_ref: NonEmptyStr  # dotted path to a callable
    kwargs: dict[str, Any] = Field(default_factory=dict)


HookImpl = HttpCallbackHook | PythonHook


class HookDefinition(OrchestratorBase):
    hook_id: str = Field(default_factory=lambda: str(__import__("uuid").uuid4()))
    event: HookEvent
    name: NonEmptyStr
    description: str | None = None
    implementation: HookImpl = Field(..., discriminator="runtime")
    enabled: bool = True
    order: int = Field(default=0, ge=0)  # lower = runs first within same event
    on_failure: Literal["ignore", "abort", "retry"] = "ignore"


# ---------------------------------------------------------------------------
# Retry / circuit-breaker policy
# ---------------------------------------------------------------------------

class RetryPolicy(OrchestratorBase):
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay_ms: int = Field(default=500, ge=0)
    max_delay_ms: int = Field(default=30_000, ge=0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    retryable_status_codes: list[int] = Field(
        default_factory=lambda: [429, 502, 503, 504]
    )

    @model_validator(mode="after")
    def delay_ordering(self) -> "RetryPolicy":
        if self.max_delay_ms < self.initial_delay_ms:
            raise ValueError("max_delay_ms must be >= initial_delay_ms")
        return self


class CircuitBreakerPolicy(OrchestratorBase):
    enabled: bool = True
    failure_threshold: int = Field(default=5, ge=1)
    success_threshold: int = Field(default=2, ge=1)  # successes needed to close
    open_duration_seconds: int = Field(default=60, ge=1)


# ---------------------------------------------------------------------------
# Full configuration template
# ---------------------------------------------------------------------------

class ConfigurationCreate(OrchestratorBase):
    tenant_id: TenantId
    adapter_id: ResourceId
    adapter_version_id: ResourceId
    name: NonEmptyStr = Field(..., max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    field_mappings: list[FieldMapping] = Field(..., min_length=1)
    hooks: list[HookDefinition] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    circuit_breaker: CircuitBreakerPolicy = Field(default_factory=CircuitBreakerPolicy)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    credentials_vault_path: str | None = Field(
        default=None,
        description="Vault path prefix where runtime credentials live, e.g. 'secret/tenants/{tid}/adapters/{aid}'",
    )
    extra_config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("field_mappings")
    @classmethod
    def no_duplicate_targets(cls, v: list[FieldMapping]) -> list[FieldMapping]:
        targets = [m.target_path for m in v]
        if len(targets) != len(set(targets)):
            dupes = [t for t in targets if targets.count(t) > 1]
            raise ValueError(f"Duplicate target_path values in field_mappings: {set(dupes)}")
        return v


class ConfigurationUpdate(OrchestratorBase):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    field_mappings: list[FieldMapping] | None = None
    hooks: list[HookDefinition] | None = None
    retry_policy: RetryPolicy | None = None
    circuit_breaker: CircuitBreakerPolicy | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    credentials_vault_path: str | None = None
    extra_config: dict[str, Any] | None = None
    tags: list[str] | None = None


class ConfigurationRead(TimestampedMixin):
    id: ResourceId
    tenant_id: TenantId
    adapter_id: ResourceId
    adapter_version_id: ResourceId
    name: NonEmptyStr
    description: str | None
    status: ConfigurationStatus
    version_number: int  # monotonically increasing per tenant+adapter pair
    field_mappings: list[FieldMapping]
    hooks: list[HookDefinition]
    retry_policy: RetryPolicy
    circuit_breaker: CircuitBreakerPolicy
    timeout_seconds: int
    credentials_vault_path: str | None
    extra_config: dict[str, Any]
    tags: list[str]


class ConfigurationListItem(OrchestratorBase):
    id: ResourceId
    tenant_id: TenantId
    adapter_id: ResourceId
    name: NonEmptyStr
    status: ConfigurationStatus
    version_number: int
    created_at: str
    updated_at: str
