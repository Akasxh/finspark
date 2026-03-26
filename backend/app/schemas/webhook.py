"""
Webhook configuration and delivery tracking schemas.
Tenants subscribe to system events; the delivery engine signs and retries.
"""
from __future__ import annotations

import hashlib
import hmac
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator

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

class WebhookEventType(StrEnum):
    # Document
    DOCUMENT_PARSED = "document.parsed"
    DOCUMENT_FAILED = "document.failed"
    # Configuration
    CONFIG_ACTIVATED = "config.activated"
    CONFIG_ROLLED_BACK = "config.rolled_back"
    # Integration runtime
    INTEGRATION_SUCCEEDED = "integration.succeeded"
    INTEGRATION_FAILED = "integration.failed"
    # Test
    TEST_RUN_COMPLETED = "test_run.completed"
    VERSION_COMPARISON_COMPLETED = "version_comparison.completed"
    # Adapter
    ADAPTER_DEPRECATED = "adapter.deprecated"
    # Tenant
    QUOTA_WARNING = "tenant.quota_warning"
    QUOTA_EXCEEDED = "tenant.quota_exceeded"


class WebhookStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    ABANDONED = "abandoned"


class SignatureAlgorithm(StrEnum):
    HMAC_SHA256 = "hmac_sha256"
    HMAC_SHA512 = "hmac_sha512"


# ---------------------------------------------------------------------------
# Webhook configuration
# ---------------------------------------------------------------------------

class WebhookRetryConfig(OrchestratorBase):
    max_attempts: int = Field(default=5, ge=1, le=20)
    initial_delay_seconds: int = Field(default=10, ge=1)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_delay_seconds: int = Field(default=3600, ge=1)

    @model_validator(mode="after")
    def delay_order(self) -> "WebhookRetryConfig":
        max_possible = self.initial_delay_seconds * (
            self.backoff_multiplier ** (self.max_attempts - 1)
        )
        # just a soft warning, not an error — log in practice
        return self


class WebhookCreate(OrchestratorBase):
    tenant_id: TenantId
    name: NonEmptyStr = Field(..., max_length=200)
    url: str = Field(..., description="HTTPS endpoint that will receive events")
    events: list[WebhookEventType] = Field(..., min_length=1)
    secret: str = Field(
        ...,
        min_length=16,
        max_length=256,
        description="Shared secret used to sign payloads (HMAC). Store this value — it won't be returned after creation.",
    )
    signature_algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256
    retry_config: WebhookRetryConfig = Field(default_factory=WebhookRetryConfig)
    custom_headers: dict[str, str] = Field(default_factory=dict, max_length=10)
    description: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("url")
    @classmethod
    def https_required(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS.")
        return v

    @field_validator("custom_headers")
    @classmethod
    def no_reserved_headers(cls, v: dict[str, str]) -> dict[str, str]:
        reserved = {
            "x-finspark-signature",
            "x-finspark-timestamp",
            "x-finspark-event",
            "content-type",
        }
        conflict = {k for k in v if k.lower() in reserved}
        if conflict:
            raise ValueError(f"Custom headers conflict with reserved names: {conflict}")
        return v

    @field_validator("events")
    @classmethod
    def deduplicate_events(cls, v: list[WebhookEventType]) -> list[WebhookEventType]:
        return list(dict.fromkeys(v))


class WebhookUpdate(OrchestratorBase):
    name: str | None = Field(default=None, max_length=200)
    url: str | None = None
    events: list[WebhookEventType] | None = None
    retry_config: WebhookRetryConfig | None = None
    custom_headers: dict[str, str] | None = None
    description: str | None = None
    tags: list[str] | None = None
    status: WebhookStatus | None = None

    @field_validator("url")
    @classmethod
    def https_if_set(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS.")
        return v


class WebhookRead(TimestampedMixin):
    id: ResourceId
    tenant_id: TenantId
    name: NonEmptyStr
    url: str
    events: list[WebhookEventType]
    signature_algorithm: SignatureAlgorithm
    retry_config: WebhookRetryConfig
    custom_headers: dict[str, str]
    description: str | None
    tags: list[str]
    status: WebhookStatus
    # secret is NEVER returned in read responses
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0
    last_delivery_at: str | None = None
    last_delivery_status: DeliveryStatus | None = None


class WebhookListItem(OrchestratorBase):
    id: ResourceId
    tenant_id: TenantId
    name: NonEmptyStr
    url: str
    events: list[WebhookEventType]
    status: WebhookStatus
    last_delivery_at: str | None
    last_delivery_status: DeliveryStatus | None


# ---------------------------------------------------------------------------
# Delivery log
# ---------------------------------------------------------------------------

class WebhookDeliveryAttempt(OrchestratorBase):
    attempt_number: int = Field(..., ge=1)
    attempted_at: str
    response_status: int | None = None
    response_body_preview: str | None = Field(default=None, max_length=500)
    duration_ms: int | None = None
    error: str | None = None


class WebhookDeliveryRead(OrchestratorBase):
    id: ResourceId
    webhook_id: ResourceId
    tenant_id: TenantId
    event_type: WebhookEventType
    payload_id: str  # idempotency key
    status: DeliveryStatus
    attempts: list[WebhookDeliveryAttempt] = Field(default_factory=list)
    next_retry_at: str | None = None
    created_at: str
    resolved_at: str | None = None


# ---------------------------------------------------------------------------
# Outbound payload envelope (what the subscriber receives)
# ---------------------------------------------------------------------------

class WebhookPayload(OrchestratorBase):
    """
    Shape of the POST body sent to the subscriber URL.
    Signed with: HMAC(secret, f"{timestamp}.{json_body}")
    Signature placed in X-FinSpark-Signature header.
    """
    id: str              # delivery ID for idempotency
    event: WebhookEventType
    tenant_id: TenantId
    api_version: str = "2025-01"
    created_at: str      # ISO-8601
    data: dict[str, Any]

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "del_01J...",
                "event": "integration.succeeded",
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "api_version": "2025-01",
                "created_at": "2025-03-26T10:00:00Z",
                "data": {"integration_id": "...", "duration_ms": 142},
            }
        }
    }
