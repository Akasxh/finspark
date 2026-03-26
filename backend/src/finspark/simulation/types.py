"""
Shared data-model types for the Simulation & Testing Framework.

Everything in this module is a pure-Pydantic / enum definition.
No I/O, no HTTP, no external deps beyond pydantic.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


class AdapterKind(str, Enum):
    CREDIT_BUREAU = "credit_bureau"
    KYC = "kyc"
    GST = "gst"
    FRAUD = "fraud"
    PAYMENT_GATEWAY = "payment_gateway"
    OPEN_BANKING = "open_banking"
    GENERIC = "generic"


class AuthScheme(str, Enum):
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    NONE = "none"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


# ---------------------------------------------------------------------------
# Adapter / integration config
# ---------------------------------------------------------------------------


class FieldMapping(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_field: str
    target_field: str
    transform: str | None = None  # e.g. "upper", "to_iso8601", custom jmespath


class EndpointSchema(BaseModel):
    """Describes one API endpoint used by an adapter."""

    path: str
    method: HttpMethod = HttpMethod.POST
    summary: str = ""
    request_schema: dict[str, Any] = Field(default_factory=dict)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    # HTTP status codes that are considered successful
    success_codes: list[int] = Field(default=[200, 201])
    latency_p50_ms: int = 120
    latency_p99_ms: int = 800
    error_rate: float = Field(default=0.02, ge=0.0, le=1.0)


class AdapterSchema(BaseModel):
    """Full schema definition for an adapter (one logical integration)."""

    adapter_id: str
    name: str
    kind: AdapterKind = AdapterKind.GENERIC
    version: str  # semver, e.g. "1.0.0"
    base_url: str
    auth_scheme: AuthScheme = AuthScheme.BEARER
    endpoints: list[EndpointSchema] = Field(default_factory=list)
    field_mappings: list[FieldMapping] = Field(default_factory=list)
    # JSON Schema for the full adapter config blob
    config_schema: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class IntegrationConfig(BaseModel):
    """
    A tenant's instantiated configuration for one adapter.
    Stored in the Integration Registry; this is the 'live config' snapshot.
    """

    config_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tenant_id: str
    adapter_id: str
    adapter_version: str
    enabled: bool = True
    # Opaque per-tenant settings (API keys, env-specific base URLs, …)
    settings: dict[str, Any] = Field(default_factory=dict)
    field_overrides: list[FieldMapping] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Simulation / test result types
# ---------------------------------------------------------------------------


class FieldAccuracy(BaseModel):
    field: str
    expected: Any = None
    actual: Any = None
    matched: bool = False
    note: str = ""


class StepResult(BaseModel):
    step_name: str
    status: StepStatus
    duration_ms: float
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None
    status_code: int | None = None
    field_accuracies: list[FieldAccuracy] = Field(default_factory=list)
    contract_violations: list[str] = Field(default_factory=list)
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def field_accuracy_score(self) -> float:
        if not self.field_accuracies:
            return 1.0
        hits = sum(1 for f in self.field_accuracies if f.matched)
        return hits / len(self.field_accuracies)


class VersionComparisonResult(BaseModel):
    """Side-by-side result of running the same request against v1 and v2."""

    request_payload: dict[str, Any]
    v1_step: StepResult
    v2_step: StepResult
    fields_diverged: list[str] = Field(default_factory=list)
    latency_delta_ms: float = 0.0
    compatible: bool = False
    notes: list[str] = Field(default_factory=list)


class SimulationReport(BaseModel):
    """Final report produced by IntegrationSimulator for one run."""

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tenant_id: str
    adapter_id: str
    adapter_version: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    steps: list[StepResult] = Field(default_factory=list)
    overall_status: StepStatus = StepStatus.SKIP
    total_duration_ms: float = 0.0
    pass_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    field_accuracy_avg: float = 0.0
    rollback_triggered: bool = False
    rollback_reason: str | None = None
    sandbox_id: str | None = None

    def finalise(self) -> None:
        self.finished_at = datetime.now(UTC)
        self.total_duration_ms = sum(s.duration_ms for s in self.steps)
        self.pass_count = sum(1 for s in self.steps if s.status == StepStatus.PASS)
        self.fail_count = sum(1 for s in self.steps if s.status == StepStatus.FAIL)
        self.error_count = sum(1 for s in self.steps if s.status == StepStatus.ERROR)
        scores = [s.field_accuracy_score for s in self.steps if s.field_accuracies]
        self.field_accuracy_avg = sum(scores) / len(scores) if scores else 1.0
        if self.error_count > 0:
            self.overall_status = StepStatus.ERROR
        elif self.fail_count > 0:
            self.overall_status = StepStatus.FAIL
        elif self.pass_count > 0:
            self.overall_status = StepStatus.PASS
        else:
            self.overall_status = StepStatus.SKIP
