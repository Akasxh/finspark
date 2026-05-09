"""Pydantic schemas for contract testing API responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DriftFieldResponse(BaseModel):
    field_path: str
    expected_type: str
    actual_type: str | None
    drift_type: str


class ContractTestResultResponse(BaseModel):
    endpoint_path: str
    http_method: str
    schema_valid: bool
    status_code: int
    response_time_ms: int
    sla_ms: int | None
    latency_ok: bool
    drift_report: list[DriftFieldResponse]
    deprecation_warnings: list[str]
    error: str | None = None


class ContractTestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    configuration_id: str
    adapter_name: str
    adapter_version: str
    total_endpoints: int
    passed: int
    failed: int
    status: str
    results: list[ContractTestResultResponse] = []
    created_at: datetime


class RunContractTestRequest(BaseModel):
    sandbox_url: str | None = None
    sla_ms: int | None = None
