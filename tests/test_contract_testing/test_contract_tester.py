"""Tests for the contract testing service.

All HTTP calls are mocked — no real APIs are hit.
"""

import json
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import Adapter, AdapterVersion
from finspark.models.api_call_log import APICallLog
from finspark.models.configuration import Configuration
from finspark.models.contract_test import ContractTestRun
from finspark.services.testing.contract_tester import ContractTester

TENANT = "test-tenant"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "credit_score": {"type": "integer"},
        "status": {"type": "string"},
        "report_id": {"type": "string"},
    },
    "required": ["credit_score", "status"],
}

REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "pan_number": {"type": "string"},
    },
    "required": ["pan_number"],
}

ENDPOINTS = [
    {"path": "/v1/credit-check", "method": "POST", "enabled": True},
]

FIELD_MAPPINGS = [
    {"source_field": "pan_number", "target_field": "pan"},
]


async def _seed_config(db: AsyncSession) -> tuple[str, str]:
    """Create adapter + version + configuration, return (config_id, av_id)."""
    adapter = Adapter(
        id="adapter-1",
        name="TestBureau",
        category="bureau",
        is_active=True,
    )
    db.add(adapter)

    av = AdapterVersion(
        id="av-1",
        adapter_id="adapter-1",
        version="v1",
        base_url="https://sandbox.testbureau.in",
        auth_type="api_key",
        request_schema=json.dumps(REQUEST_SCHEMA),
        response_schema=json.dumps(RESPONSE_SCHEMA),
        endpoints=json.dumps(ENDPOINTS),
    )
    db.add(av)

    config = Configuration(
        id="cfg-1",
        tenant_id=TENANT,
        name="Test Config",
        adapter_version_id="av-1",
        status="active",
        version=1,
        field_mappings=json.dumps(FIELD_MAPPINGS),
        full_config=json.dumps({
            "adapter_name": "TestBureau",
            "version": "v1",
            "base_url": "https://sandbox.testbureau.in",
            "auth": {"type": "api_key", "credentials": {"api_key": "test-key"}},
            "endpoints": ENDPOINTS,
            "field_mappings": FIELD_MAPPINGS,
        }),
    )
    db.add(config)
    await db.flush()
    return "cfg-1", "av-1"


def _mock_response(
    status: int = 200,
    body: dict | None = None,
    headers: dict | None = None,
    delay_ms: int = 0,
) -> httpx.Response:
    resp_headers = dict(headers or {})
    return httpx.Response(
        status_code=status,
        json=body or {},
        headers=resp_headers,
        request=httpx.Request("POST", "https://sandbox.testbureau.in/v1/credit-check"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_contract_test_all_pass(db_session: AsyncSession) -> None:
    """Mock response matches schema exactly -> all pass, no drift."""
    await _seed_config(db_session)

    matching_body = {"credit_score": 750, "status": "ok", "report_id": "RPT-1"}
    resp = _mock_response(body=matching_body)

    with patch("finspark.services.testing.contract_tester.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        tester = ContractTester(db_session)
        result = await tester.run_contract_test("cfg-1", TENANT)

    assert result.total_endpoints == 1
    assert result.passed == 1
    assert result.failed == 0
    assert result.results[0].schema_valid is True
    assert result.results[0].drift_report == []
    assert result.results[0].status_code == 200


@pytest.mark.asyncio
async def test_run_contract_test_schema_drift_type_changed(db_session: AsyncSession) -> None:
    """credit_score returned as string instead of integer -> type_changed drift."""
    await _seed_config(db_session)

    drift_body = {"credit_score": "750", "status": "ok", "report_id": "RPT-1"}
    resp = _mock_response(body=drift_body)

    with patch("finspark.services.testing.contract_tester.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        tester = ContractTester(db_session)
        result = await tester.run_contract_test("cfg-1", TENANT)

    assert result.failed == 1
    drift = result.results[0].drift_report
    type_drifts = [d for d in drift if d.drift_type == "type_changed"]
    assert len(type_drifts) == 1
    assert type_drifts[0].field_path == "credit_score"
    assert type_drifts[0].expected_type == "integer"
    assert type_drifts[0].actual_type == "string"


@pytest.mark.asyncio
async def test_run_contract_test_field_removed(db_session: AsyncSession) -> None:
    """Response missing a schema-expected field -> field_removed drift."""
    await _seed_config(db_session)

    missing_body = {"status": "ok"}  # credit_score and report_id absent
    resp = _mock_response(body=missing_body)

    with patch("finspark.services.testing.contract_tester.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        tester = ContractTester(db_session)
        result = await tester.run_contract_test("cfg-1", TENANT)

    assert result.failed == 1
    removed = [d for d in result.results[0].drift_report if d.drift_type == "field_removed"]
    assert len(removed) == 2
    removed_names = {d.field_path for d in removed}
    assert "credit_score" in removed_names
    assert "report_id" in removed_names


@pytest.mark.asyncio
async def test_run_contract_test_field_added(db_session: AsyncSession) -> None:
    """Response has extra field not in schema -> field_added drift."""
    await _seed_config(db_session)

    extra_body = {
        "credit_score": 750,
        "status": "ok",
        "report_id": "RPT-1",
        "surprise_field": "unexpected",
    }
    resp = _mock_response(body=extra_body)

    with patch("finspark.services.testing.contract_tester.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        tester = ContractTester(db_session)
        result = await tester.run_contract_test("cfg-1", TENANT)

    assert result.failed == 1
    added = [d for d in result.results[0].drift_report if d.drift_type == "field_added"]
    assert len(added) == 1
    assert added[0].field_path == "surprise_field"


@pytest.mark.asyncio
async def test_deprecation_header_detection(db_session: AsyncSession) -> None:
    """Sunset header in response -> deprecation warning generated."""
    await _seed_config(db_session)

    body = {"credit_score": 750, "status": "ok", "report_id": "RPT-1"}
    resp = _mock_response(body=body, headers={"Sunset": "2025-12-31"})

    with patch("finspark.services.testing.contract_tester.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        tester = ContractTester(db_session)
        result = await tester.run_contract_test("cfg-1", TENANT)

    warnings = result.results[0].deprecation_warnings
    assert len(warnings) >= 1
    assert any("Sunset" in w for w in warnings)


@pytest.mark.asyncio
async def test_latency_drift(db_session: AsyncSession) -> None:
    """Response slower than SLA -> latency_ok=False."""
    await _seed_config(db_session)

    body = {"credit_score": 750, "status": "ok", "report_id": "RPT-1"}
    resp = _mock_response(body=body)

    async def slow_request(*args: object, **kwargs: object) -> httpx.Response:
        # Simulate latency by sleeping briefly
        import asyncio
        await asyncio.sleep(0.05)  # 50ms
        return resp

    with patch("finspark.services.testing.contract_tester.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request.side_effect = slow_request
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        tester = ContractTester(db_session)
        # SLA of 10ms — the 50ms mock will exceed it
        result = await tester.run_contract_test("cfg-1", TENANT, sla_ms=10)

    assert result.results[0].latency_ok is False
    assert result.results[0].response_time_ms >= 10


@pytest.mark.asyncio
async def test_sample_request_generation(db_session: AsyncSession) -> None:
    """Verify _generate_sample_request produces plausible Indian fintech test data."""
    tester = ContractTester(db_session)

    mappings = [
        {"source_field": "pan_number", "target_field": "pan"},
        {"source_field": "email", "target_field": "email_address"},
        {"source_field": "unknown_field", "target_field": "some_target"},
    ]
    schema = {
        "type": "object",
        "properties": {
            "pan": {"type": "string"},
            "amount": {"type": "integer"},
        },
        "required": ["pan", "amount"],
    }

    result = tester._generate_sample_request(mappings, schema)

    # pan should be set from SAMPLE_DATA
    assert result["pan"] == "TESTX1234Z"
    # email_address should be set from SAMPLE_DATA
    assert result["email_address"] == "test@example.com"
    # unknown field gets a placeholder
    assert result["some_target"] == "sample_some_target"
    # amount from required schema field filled from SAMPLE_DATA
    assert result["amount"] == 10000


@pytest.mark.asyncio
async def test_contract_test_stored(db_session: AsyncSession) -> None:
    """Verify contract test result is persisted to the database via API route."""
    await _seed_config(db_session)

    body = {"credit_score": 750, "status": "ok", "report_id": "RPT-1"}
    resp = _mock_response(body=body)

    with patch("finspark.services.testing.contract_tester.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        tester = ContractTester(db_session)
        result = await tester.run_contract_test("cfg-1", TENANT)

    # Persist manually (mimicking what the route does)
    from dataclasses import asdict

    run = ContractTestRun(
        tenant_id=TENANT,
        configuration_id="cfg-1",
        adapter_name=result.adapter_name,
        adapter_version=result.adapter_version,
        total_endpoints=result.total_endpoints,
        passed=result.passed,
        failed=result.failed,
        results=json.dumps([asdict(r) for r in result.results]),
        status="passed" if result.failed == 0 else "failed",
    )
    db_session.add(run)
    await db_session.flush()

    # Verify persisted
    stmt = select(ContractTestRun).where(ContractTestRun.tenant_id == TENANT)
    db_result = await db_session.execute(stmt)
    stored = db_result.scalar_one()
    assert stored.status == "passed"
    assert stored.passed == 1
    assert stored.configuration_id == "cfg-1"
    assert stored.adapter_name == "TestBureau"

    # Verify results JSON is parseable
    parsed = json.loads(stored.results)
    assert len(parsed) == 1
    assert parsed[0]["schema_valid"] is True

    # Also verify CallLogger created a log entry
    log_stmt = select(APICallLog).where(APICallLog.tenant_id == TENANT)
    log_result = await db_session.execute(log_stmt)
    logs = log_result.scalars().all()
    assert len(logs) == 1
    assert logs[0].adapter_name == "TestBureau"
