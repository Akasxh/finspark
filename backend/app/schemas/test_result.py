"""
Test/simulation result schemas.
Covers single-run results, parallel multi-version comparison runs,
mock API behaviour definitions, and rollback triggers.
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

class TestRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    ABORTED = "aborted"
    TIMEOUT = "timeout"


class TestRunMode(StrEnum):
    UNIT = "unit"            # single configuration, mocked external
    INTEGRATION = "integration"  # real external service in staging
    SIMULATION = "simulation"    # full synthetic dataset, no real calls
    CANARY = "canary"            # real traffic %, side-by-side


class AssertionType(StrEnum):
    STATUS_CODE = "status_code"
    JSON_PATH = "json_path"
    RESPONSE_TIME_MS = "response_time_ms"
    SCHEMA_VALID = "schema_valid"
    FIELD_PRESENT = "field_present"
    FIELD_ABSENT = "field_absent"
    CUSTOM_EXPRESSION = "custom_expression"


class MockBehaviour(StrEnum):
    STATIC = "static"           # fixed response
    RANDOM_FROM_SET = "random"  # pick randomly from fixtures
    SEQUENCE = "sequence"       # rotate through fixtures in order
    ERROR_RATE = "error_rate"   # return error N% of the time
    LATENCY_INJECT = "latency"  # add artificial delay


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

class StatusCodeAssertion(OrchestratorBase):
    type: Literal[AssertionType.STATUS_CODE] = AssertionType.STATUS_CODE
    expected: int = Field(..., ge=100, le=599)


class JsonPathAssertion(OrchestratorBase):
    type: Literal[AssertionType.JSON_PATH] = AssertionType.JSON_PATH
    path: NonEmptyStr      # JMESPath expression
    expected_value: Any | None = None
    operator: Literal["eq", "ne", "gt", "lt", "contains", "exists"] = "eq"


class ResponseTimeAssertion(OrchestratorBase):
    type: Literal[AssertionType.RESPONSE_TIME_MS] = AssertionType.RESPONSE_TIME_MS
    max_ms: int = Field(..., ge=1)


class SchemaValidAssertion(OrchestratorBase):
    type: Literal[AssertionType.SCHEMA_VALID] = AssertionType.SCHEMA_VALID
    json_schema: dict[str, Any]


class FieldPresentAssertion(OrchestratorBase):
    type: Literal[AssertionType.FIELD_PRESENT] = AssertionType.FIELD_PRESENT
    path: NonEmptyStr


class FieldAbsentAssertion(OrchestratorBase):
    type: Literal[AssertionType.FIELD_ABSENT] = AssertionType.FIELD_ABSENT
    path: NonEmptyStr


class CustomExprAssertion(OrchestratorBase):
    type: Literal[AssertionType.CUSTOM_EXPRESSION] = AssertionType.CUSTOM_EXPRESSION
    expression: NonEmptyStr  # evaluated with `response` in scope


TestAssertion = (
    StatusCodeAssertion
    | JsonPathAssertion
    | ResponseTimeAssertion
    | SchemaValidAssertion
    | FieldPresentAssertion
    | FieldAbsentAssertion
    | CustomExprAssertion
)


# ---------------------------------------------------------------------------
# Mock API definition
# ---------------------------------------------------------------------------

class MockResponseFixture(OrchestratorBase):
    status_code: int = Field(default=200, ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    delay_ms: int = Field(default=0, ge=0)
    label: str | None = None  # human-readable name for this fixture


class MockEndpointConfig(OrchestratorBase):
    endpoint_id: NonEmptyStr  # matches AdapterEndpoint.endpoint_id
    behaviour: MockBehaviour = MockBehaviour.STATIC
    fixtures: list[MockResponseFixture] = Field(..., min_length=1)
    error_rate_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    base_latency_ms: int = Field(default=50, ge=0)
    latency_jitter_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def sequence_needs_fixtures(self) -> "MockEndpointConfig":
        if self.behaviour == MockBehaviour.RANDOM_FROM_SET and len(self.fixtures) < 2:
            raise ValueError("RANDOM_FROM_SET behaviour requires at least 2 fixtures.")
        return self


# ---------------------------------------------------------------------------
# Test case
# ---------------------------------------------------------------------------

class TestCase(OrchestratorBase):
    test_case_id: str = Field(default_factory=lambda: str(__import__("uuid").uuid4()))
    name: NonEmptyStr
    description: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    input_headers: dict[str, str] = Field(default_factory=dict)
    assertions: list[TestAssertion] = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    skip: bool = False
    timeout_ms: int = Field(default=30_000, ge=1_000)


# ---------------------------------------------------------------------------
# Test run request
# ---------------------------------------------------------------------------

class TestRunCreate(OrchestratorBase):
    tenant_id: TenantId
    configuration_id: ResourceId
    mode: TestRunMode = TestRunMode.SIMULATION
    test_cases: list[TestCase] = Field(..., min_length=1, max_length=500)
    mock_configs: list[MockEndpointConfig] = Field(default_factory=list)
    parallel_workers: int = Field(default=4, ge=1, le=32)
    abort_on_first_failure: bool = False
    description: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-assertion and per-case results
# ---------------------------------------------------------------------------

class AssertionResult(OrchestratorBase):
    assertion_type: AssertionType
    passed: bool
    expected: Any | None = None
    actual: Any | None = None
    message: str | None = None


class TestCaseResult(OrchestratorBase):
    test_case_id: str
    name: NonEmptyStr
    status: TestRunStatus
    duration_ms: int
    assertion_results: list[AssertionResult]
    request_dump: dict[str, Any] | None = None   # sanitised request for debugging
    response_dump: dict[str, Any] | None = None  # sanitised response
    error: str | None = None
    error_type: str | None = None


# ---------------------------------------------------------------------------
# Full test run result
# ---------------------------------------------------------------------------

class TestRunRead(TimestampedMixin):
    id: ResourceId
    tenant_id: TenantId
    configuration_id: ResourceId
    mode: TestRunMode
    status: TestRunStatus
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    skipped_cases: int
    duration_ms: int | None
    case_results: list[TestCaseResult] = Field(default_factory=list)
    description: str | None
    tags: list[str]
    started_at: str | None
    completed_at: str | None

    @model_validator(mode="after")
    def counts_consistent(self) -> "TestRunRead":
        declared = self.passed_cases + self.failed_cases + self.error_cases + self.skipped_cases
        if declared != self.total_cases:
            raise ValueError(
                f"Case counts don't sum to total: {declared} != {self.total_cases}"
            )
        return self


class TestRunListItem(OrchestratorBase):
    id: ResourceId
    tenant_id: TenantId
    configuration_id: ResourceId
    mode: TestRunMode
    status: TestRunStatus
    total_cases: int
    passed_cases: int
    failed_cases: int
    duration_ms: int | None
    created_at: str


# ---------------------------------------------------------------------------
# Multi-version parallel comparison
# ---------------------------------------------------------------------------

class VersionTestTarget(OrchestratorBase):
    adapter_version_id: ResourceId
    version: SemVer
    configuration_id: ResourceId
    is_baseline: bool = False  # exactly one target should be baseline


class VersionComparisonRunCreate(OrchestratorBase):
    tenant_id: TenantId
    name: NonEmptyStr
    targets: list[VersionTestTarget] = Field(..., min_length=2, max_length=10)
    test_cases: list[TestCase] = Field(..., min_length=1, max_length=200)
    mock_configs: list[MockEndpointConfig] = Field(default_factory=list)
    description: str | None = None

    @field_validator("targets")
    @classmethod
    def exactly_one_baseline(cls, v: list[VersionTestTarget]) -> list[VersionTestTarget]:
        baselines = [t for t in v if t.is_baseline]
        if len(baselines) != 1:
            raise ValueError(
                f"Exactly one target must be marked is_baseline=True, got {len(baselines)}."
            )
        return v

    @model_validator(mode="after")
    def unique_versions(self) -> "VersionComparisonRunCreate":
        versions = [t.version for t in self.targets]
        if len(versions) != len(set(versions)):
            raise ValueError("Duplicate versions in comparison targets.")
        return self


class VersionComparisonResult(OrchestratorBase):
    """
    Side-by-side diff of two adapter versions across a shared test suite.
    """
    id: ResourceId
    tenant_id: TenantId
    name: NonEmptyStr
    baseline_version: SemVer
    candidate_version: SemVer
    baseline_run_id: ResourceId
    candidate_run_id: ResourceId
    total_cases: int
    both_passed: int
    baseline_only_passed: int   # regressions in candidate
    candidate_only_passed: int  # improvements in candidate
    both_failed: int
    p99_latency_baseline_ms: float | None
    p99_latency_candidate_ms: float | None
    latency_delta_percent: float | None   # (candidate - baseline) / baseline * 100
    breaking_change_detected: bool
    breaking_change_details: list[str] = Field(default_factory=list)
    recommendation: Literal["promote", "hold", "rollback"] | None = None
    created_at: str
