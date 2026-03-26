"""
API request/response envelope models for all HTTP endpoints.
Groups endpoint schemas by router domain and provides typed
request bodies / response wrappers used by FastAPI route handlers.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import Field

from .adapter import AdapterCreate, AdapterListItem, AdapterRead, AdapterUpdate, AdapterVersionCreate, AdapterVersionRead
from .audit_log import AuditLogListItem, AuditLogQueryParams, AuditLogRead
from .common import OrchestratorBase, Page, ResourceId, SuccessResponse, TenantId
from .configuration import ConfigurationCreate, ConfigurationListItem, ConfigurationRead, ConfigurationUpdate
from .document import DocumentListItem, DocumentRead, DocumentUploadRequest, DocumentUploadResponse
from .tenant import TenantCreate, TenantListItem, TenantRead, TenantUpdate
from .test_result import (
    TestRunCreate,
    TestRunListItem,
    TestRunRead,
    VersionComparisonResult,
    VersionComparisonRunCreate,
)
from .version_comparison import (
    AdapterVersionDiff,
    AdapterVersionDiffRequest,
    ConfigVersionDiff,
    ConfigVersionDiffRequest,
    PromotionRecord,
    PromotionRequest,
    RollbackRequest,
)
from .webhook import (
    WebhookCreate,
    WebhookDeliveryRead,
    WebhookListItem,
    WebhookRead,
    WebhookUpdate,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthCheck(OrchestratorBase):
    status: str = "ok"
    version: str
    environment: str
    db_reachable: bool
    redis_reachable: bool
    uptime_seconds: float


# ---------------------------------------------------------------------------
# Tenant API
# ---------------------------------------------------------------------------

class TenantCreateRequest(TenantCreate):
    pass


class TenantCreateResponse(SuccessResponse[TenantRead]):
    pass


class TenantReadResponse(SuccessResponse[TenantRead]):
    pass


class TenantListResponse(SuccessResponse[Page[TenantListItem]]):
    pass


class TenantUpdateRequest(TenantUpdate):
    pass


class TenantUpdateResponse(SuccessResponse[TenantRead]):
    pass


# ---------------------------------------------------------------------------
# Document API
# ---------------------------------------------------------------------------

class DocumentUploadInitRequest(DocumentUploadRequest):
    pass


class DocumentUploadInitResponse(SuccessResponse[DocumentUploadResponse]):
    pass


class DocumentReadResponse(SuccessResponse[DocumentRead]):
    pass


class DocumentListResponse(SuccessResponse[Page[DocumentListItem]]):
    pass


class DocumentRetriggerParseResponse(SuccessResponse[dict[str, str]]):
    """Returns {"task_id": "..."} pointing to the async parse job."""
    pass


# ---------------------------------------------------------------------------
# Adapter API
# ---------------------------------------------------------------------------

class AdapterCreateRequest(AdapterCreate):
    initial_version: AdapterVersionCreate | None = None


class AdapterCreateResponse(SuccessResponse[AdapterRead]):
    pass


class AdapterReadResponse(SuccessResponse[AdapterRead]):
    pass


class AdapterListResponse(SuccessResponse[Page[AdapterListItem]]):
    pass


class AdapterUpdateRequest(AdapterUpdate):
    pass


class AdapterUpdateResponse(SuccessResponse[AdapterRead]):
    pass


class AdapterVersionCreateRequest(AdapterVersionCreate):
    pass


class AdapterVersionCreateResponse(SuccessResponse[AdapterVersionRead]):
    pass


class AdapterVersionListResponse(SuccessResponse[list[AdapterVersionRead]]):
    pass


# ---------------------------------------------------------------------------
# Configuration API
# ---------------------------------------------------------------------------

class ConfigurationCreateRequest(ConfigurationCreate):
    pass


class ConfigurationCreateResponse(SuccessResponse[ConfigurationRead]):
    pass


class ConfigurationReadResponse(SuccessResponse[ConfigurationRead]):
    pass


class ConfigurationListResponse(SuccessResponse[Page[ConfigurationListItem]]):
    pass


class ConfigurationUpdateRequest(ConfigurationUpdate):
    pass


class ConfigurationUpdateResponse(SuccessResponse[ConfigurationRead]):
    pass


class ConfigurationActivateResponse(SuccessResponse[ConfigurationRead]):
    pass


class ConfigurationDiffResponse(SuccessResponse[ConfigVersionDiff]):
    pass


# ---------------------------------------------------------------------------
# Test run API
# ---------------------------------------------------------------------------

class TestRunCreateRequest(TestRunCreate):
    pass


class TestRunCreateResponse(SuccessResponse[dict[str, str]]):
    """Async — returns {"run_id": "...", "status_url": "..."}"""
    pass


class TestRunReadResponse(SuccessResponse[TestRunRead]):
    pass


class TestRunListResponse(SuccessResponse[Page[TestRunListItem]]):
    pass


class TestRunAbortResponse(SuccessResponse[dict[str, str]]):
    pass


class VersionComparisonCreateRequest(VersionComparisonRunCreate):
    pass


class VersionComparisonReadResponse(SuccessResponse[VersionComparisonResult]):
    pass


# ---------------------------------------------------------------------------
# Adapter version diff API
# ---------------------------------------------------------------------------

class AdapterVersionDiffResponse(SuccessResponse[AdapterVersionDiff]):
    pass


# ---------------------------------------------------------------------------
# Promotion / rollback API
# ---------------------------------------------------------------------------

class PromotionRequestBody(PromotionRequest):
    pass


class PromotionResponse(SuccessResponse[PromotionRecord]):
    pass


class RollbackRequestBody(RollbackRequest):
    pass


class RollbackResponse(SuccessResponse[PromotionRecord]):
    pass


# ---------------------------------------------------------------------------
# Webhook API
# ---------------------------------------------------------------------------

class WebhookCreateRequest(WebhookCreate):
    pass


class WebhookCreateResponse(SuccessResponse[WebhookRead]):
    pass


class WebhookReadResponse(SuccessResponse[WebhookRead]):
    pass


class WebhookListResponse(SuccessResponse[Page[WebhookListItem]]):
    pass


class WebhookUpdateRequest(WebhookUpdate):
    pass


class WebhookUpdateResponse(SuccessResponse[WebhookRead]):
    pass


class WebhookDeliveryListResponse(SuccessResponse[Page[WebhookDeliveryRead]]):
    pass


class WebhookReplayRequest(OrchestratorBase):
    delivery_id: ResourceId


class WebhookReplayResponse(SuccessResponse[dict[str, str]]):
    pass


# ---------------------------------------------------------------------------
# Audit log API
# ---------------------------------------------------------------------------

class AuditLogReadResponse(SuccessResponse[AuditLogRead]):
    pass


class AuditLogListResponse(SuccessResponse[Page[AuditLogListItem]]):
    pass


# ---------------------------------------------------------------------------
# AI auto-config API
# ---------------------------------------------------------------------------

class AutoConfigRequest(OrchestratorBase):
    """Trigger AI-assisted configuration generation from parsed documents."""
    tenant_id: TenantId
    document_ids: list[ResourceId] = Field(..., min_length=1, max_length=10)
    adapter_id: ResourceId
    adapter_version_id: ResourceId
    configuration_name: str | None = None
    dry_run: bool = False
    confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)


class AutoConfigSuggestion(OrchestratorBase):
    configuration_id: ResourceId | None = None  # None when dry_run=True
    confidence: float
    field_mappings_generated: int
    hooks_generated: int
    low_confidence_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    dry_run_preview: dict[str, Any] | None = None


class AutoConfigResponse(SuccessResponse[AutoConfigSuggestion]):
    pass
