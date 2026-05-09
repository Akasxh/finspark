"""Contract tester — hits real/sandbox endpoints and validates against stored schemas."""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import jsonschema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finspark.models.adapter import Adapter, AdapterVersion
from finspark.models.configuration import Configuration
from finspark.services.observability.call_logger import CallLogger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DriftField:
    field_path: str
    expected_type: str
    actual_type: str | None
    drift_type: str  # type_changed | field_added | field_removed


@dataclass
class ContractTestResult:
    endpoint_path: str
    http_method: str
    schema_valid: bool
    status_code: int
    response_time_ms: int
    sla_ms: int | None
    latency_ok: bool
    drift_report: list[DriftField]
    deprecation_warnings: list[str]
    error: str | None = None


@dataclass
class ContractTestRunResult:
    configuration_id: str
    adapter_name: str
    adapter_version: str
    total_endpoints: int
    passed: int
    failed: int
    results: list[ContractTestResult]
    run_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Sample data for Indian fintech test payloads
# ---------------------------------------------------------------------------

_SAMPLE_DATA: dict[str, Any] = {
    "pan": "TESTX1234Z",
    "pan_number": "TESTX1234Z",
    "aadhaar": "999999999999",
    "aadhaar_number": "999999999999",
    "phone": "9999999999",
    "mobile": "9999999999",
    "mobile_number": "9999999999",
    "email": "test@example.com",
    "email_address": "test@example.com",
    "name": "Test User",
    "customer_name": "Test User",
    "full_name": "Test User",
    "amount": 10000,
    "loan_amount": 10000,
}

_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def _python_type_name(value: Any) -> str:
    """Map a Python value to a JSON Schema type string."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "unknown"


# ---------------------------------------------------------------------------
# ContractTester
# ---------------------------------------------------------------------------


class ContractTester:
    """Runs live contract tests against real or sandbox API endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run_contract_test(
        self,
        config_id: str,
        tenant_id: str,
        sandbox_url: str | None = None,
        sla_ms: int | None = None,
    ) -> ContractTestRunResult:
        """Run contract tests for every endpoint in the configuration.

        1. Load config + adapter version
        2. For each endpoint:
           a. Build request from field_mappings
           b. Hit the real endpoint (or sandbox_url override)
           c. Validate response against AdapterVersion.response_schema
           d. Deep-diff response structure to find drift
           e. Check Sunset / Deprecation headers
           f. Compare response time against SLA
        3. Log all calls via CallLogger
        4. Return aggregated result
        """
        config, adapter_version, adapter = await self._load_config_and_adapter(
            config_id, tenant_id
        )

        full_config: dict[str, Any] = json.loads(config.full_config) if config.full_config else {}
        field_mappings: list[dict[str, Any]] = (
            json.loads(config.field_mappings) if config.field_mappings else []
        )
        endpoints: list[dict[str, Any]] = (
            json.loads(adapter_version.endpoints) if adapter_version.endpoints else []
        )
        response_schema: dict[str, Any] = (
            json.loads(adapter_version.response_schema) if adapter_version.response_schema else {}
        )
        request_schema: dict[str, Any] = (
            json.loads(adapter_version.request_schema) if adapter_version.request_schema else {}
        )

        base_url = sandbox_url or full_config.get("base_url", "") or adapter_version.base_url or ""
        call_logger = CallLogger(self.session)

        results: list[ContractTestResult] = []
        for ep in endpoints:
            if not ep.get("enabled", True):
                continue
            result = await self._test_endpoint(
                endpoint=ep,
                base_url=base_url,
                field_mappings=field_mappings,
                request_schema=request_schema,
                response_schema=response_schema,
                full_config=full_config,
                sla_ms=sla_ms,
            )
            results.append(result)

            # Log via CallLogger
            await call_logger.log_call(
                tenant_id=tenant_id,
                configuration_id=config_id,
                adapter_name=adapter.name,
                adapter_version=adapter_version.version,
                endpoint_path=ep.get("path", ""),
                http_method=ep.get("method", "POST"),
                request_headers=None,
                request_body=None,
                response_status=result.status_code,
                response_headers=None,
                response_body=None,
                response_time_ms=result.response_time_ms,
                schema_match=result.schema_valid,
                drift_fields=(
                    {d.field_path: d.drift_type for d in result.drift_report}
                    if result.drift_report
                    else None
                ),
                error_message=result.error,
            )

        passed = sum(1 for r in results if r.schema_valid and not r.error)
        failed = len(results) - passed

        return ContractTestRunResult(
            configuration_id=config_id,
            adapter_name=adapter.name,
            adapter_version=adapter_version.version,
            total_endpoints=len(results),
            passed=passed,
            failed=failed,
            results=results,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _load_config_and_adapter(
        self, config_id: str, tenant_id: str
    ) -> tuple[Configuration, AdapterVersion, Adapter]:
        stmt = select(Configuration).where(
            Configuration.id == config_id,
            Configuration.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            raise ValueError(f"Configuration {config_id} not found")

        av_stmt = (
            select(AdapterVersion)
            .options(selectinload(AdapterVersion.adapter))
            .where(AdapterVersion.id == config.adapter_version_id)
        )
        av_result = await self.session.execute(av_stmt)
        adapter_version = av_result.scalar_one_or_none()
        if adapter_version is None:
            raise ValueError(f"AdapterVersion {config.adapter_version_id} not found")

        return config, adapter_version, adapter_version.adapter

    async def _test_endpoint(
        self,
        endpoint: dict[str, Any],
        base_url: str,
        field_mappings: list[dict[str, Any]],
        request_schema: dict[str, Any],
        response_schema: dict[str, Any],
        full_config: dict[str, Any],
        sla_ms: int | None,
    ) -> ContractTestResult:
        path = endpoint.get("path", "")
        method = endpoint.get("method", "POST").upper()
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        sample_body = self._generate_sample_request(field_mappings, request_schema)

        auth_config = full_config.get("auth", {})
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if auth_config.get("type") == "api_key":
            creds = auth_config.get("credentials", {})
            key = creds.get("api_key", "")
            header_name = creds.get("header_name", "X-API-Key")
            if key:
                headers[header_name] = key
        elif auth_config.get("type") == "bearer":
            token = auth_config.get("credentials", {}).get("token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                start = time.monotonic()
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=sample_body if method in ("POST", "PUT", "PATCH") else None,
                )
                elapsed_ms = int((time.monotonic() - start) * 1000)

            resp_headers = dict(response.headers)
            try:
                resp_body = response.json()
            except Exception:
                resp_body = {}

            # Schema validation
            schema_valid = True
            if response_schema:
                try:
                    jsonschema.validate(instance=resp_body, schema=response_schema)
                except jsonschema.ValidationError:
                    schema_valid = False

            drift_report = self._detect_drift(resp_body, response_schema) if response_schema else []
            deprecation_warnings = self._check_deprecation_headers(resp_headers)
            latency_ok = elapsed_ms <= sla_ms if sla_ms is not None else True

            return ContractTestResult(
                endpoint_path=path,
                http_method=method,
                schema_valid=schema_valid and not drift_report,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                sla_ms=sla_ms,
                latency_ok=latency_ok,
                drift_report=drift_report,
                deprecation_warnings=deprecation_warnings,
            )

        except httpx.HTTPError as exc:
            return ContractTestResult(
                endpoint_path=path,
                http_method=method,
                schema_valid=False,
                status_code=0,
                response_time_ms=0,
                sla_ms=sla_ms,
                latency_ok=False,
                drift_report=[],
                deprecation_warnings=[],
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def _detect_drift(
        self, response_body: dict[str, Any], expected_schema: dict[str, Any]
    ) -> list[DriftField]:
        """Walk the response body against the expected JSON Schema and find field-level drift."""
        drifts: list[DriftField] = []
        properties = expected_schema.get("properties", {})

        # Fields expected by schema but absent in response
        for field_name, field_def in properties.items():
            if field_name not in response_body:
                expected_type = field_def.get("type", "unknown")
                drifts.append(
                    DriftField(
                        field_path=field_name,
                        expected_type=expected_type,
                        actual_type=None,
                        drift_type="field_removed",
                    )
                )
            else:
                expected_type = field_def.get("type", "unknown")
                actual_type = _python_type_name(response_body[field_name])
                if expected_type != actual_type:
                    drifts.append(
                        DriftField(
                            field_path=field_name,
                            expected_type=expected_type,
                            actual_type=actual_type,
                            drift_type="type_changed",
                        )
                    )

        # Fields present in response but not in schema
        for field_name in response_body:
            if field_name not in properties:
                actual_type = _python_type_name(response_body[field_name])
                drifts.append(
                    DriftField(
                        field_path=field_name,
                        expected_type="N/A",
                        actual_type=actual_type,
                        drift_type="field_added",
                    )
                )

        return drifts

    # ------------------------------------------------------------------
    # Deprecation header detection
    # ------------------------------------------------------------------

    @staticmethod
    def _check_deprecation_headers(headers: dict[str, str]) -> list[str]:
        """Check for Sunset, Deprecation, or X-Deprecated response headers."""
        warnings: list[str] = []
        lower_headers = {k.lower(): v for k, v in headers.items()}

        if "sunset" in lower_headers:
            warnings.append(f"Sunset header present: {lower_headers['sunset']}")
        if "deprecation" in lower_headers:
            warnings.append(f"Deprecation header present: {lower_headers['deprecation']}")
        if "x-deprecated" in lower_headers:
            warnings.append(f"X-Deprecated header present: {lower_headers['x-deprecated']}")

        return warnings

    # ------------------------------------------------------------------
    # Sample request generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_sample_request(
        field_mappings: list[dict[str, Any]],
        request_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build a plausible test request from field mappings and optional schema."""
        payload: dict[str, Any] = {}

        # Use field mappings first — they define what the adapter expects
        for mapping in field_mappings:
            target = mapping.get("target_field", "")
            source = mapping.get("source_field", "")
            key = target or source
            if not key:
                continue
            # Check known sample data by either source or target name
            value = _SAMPLE_DATA.get(key) or _SAMPLE_DATA.get(source)
            if value is not None:
                payload[key] = value
            else:
                payload[key] = f"sample_{key}"

        # Fill any additional required fields from schema
        if request_schema:
            required = request_schema.get("required", [])
            properties = request_schema.get("properties", {})
            for field_name in required:
                if field_name not in payload:
                    if field_name in _SAMPLE_DATA:
                        payload[field_name] = _SAMPLE_DATA[field_name]
                    else:
                        field_type = properties.get(field_name, {}).get("type", "string")
                        payload[field_name] = _default_for_type(field_type)

        return payload


def _default_for_type(json_type: str) -> Any:
    """Return a sensible default for a JSON Schema type."""
    defaults: dict[str, Any] = {
        "string": "test_value",
        "integer": 0,
        "number": 0.0,
        "boolean": True,
        "array": [],
        "object": {},
    }
    return defaults.get(json_type, "test_value")
