"""
Pydantic schemas for the /simulations API surface.

A simulation runs an integration configuration in a sandboxed environment,
capturing request/response pairs and pass/fail assertions.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from finspark.schemas.common import PaginatedResponse


class SimulationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


# ---------------------------------------------------------------------------
# Run request
# ---------------------------------------------------------------------------


class AssertionSpec(BaseModel):
    """A single pass/fail assertion evaluated against the integration response."""

    path: str = Field(..., description="JSONPath expression, e.g. $.status")
    op: str = Field(..., pattern="^(eq|neq|gt|lt|gte|lte|exists|regex)$")
    expected: Any = None


class SimulationRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: UUID
    config_id: UUID
    scenario: str = Field(
        default="default",
        description="Named test scenario; maps to a fixture in the adapter's test suite.",
    )
    payload_override: dict[str, Any] = Field(
        default_factory=dict,
        description="Overrides for the simulated request body.",
    )
    assertions: list[AssertionSpec] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    mock_external: bool = Field(
        default=True,
        description="If true, external calls are intercepted by the mock layer.",
    )


# ---------------------------------------------------------------------------
# Status / results
# ---------------------------------------------------------------------------


class StepResult(BaseModel):
    step_name: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    request_snapshot: dict[str, Any] | None = None
    response_snapshot: dict[str, Any] | None = None
    status_code: int | None = None
    passed: bool | None = None
    assertion_failures: list[str] = Field(default_factory=list)
    error: str | None = None


class SimulationRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    tenant_id: UUID
    config_id: UUID
    scenario: str
    status: SimulationStatus
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    pass_count: int = 0
    fail_count: int = 0
    error: str | None = None


class SimulationDetail(SimulationRecord):
    """Full result including per-step traces."""

    steps: list[StepResult] = Field(default_factory=list)
    coverage_percent: float | None = None
    report_url: str | None = None


SimulationListResponse = PaginatedResponse[SimulationRecord]
