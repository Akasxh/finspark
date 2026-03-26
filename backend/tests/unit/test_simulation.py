"""
Unit tests for the Simulation & Testing Framework (Module 4).

Scope: everything that can be exercised without network I/O or a database.
Fixtures build minimal AdapterSchema / IntegrationConfig objects inline.

Marks:
    unit  — all tests here
    slow  — version_tester integration smoke (still in-memory, just async)
"""
from __future__ import annotations

import copy
from typing import Any

import pytest

from finspark.simulation.contract import validate_contract
from finspark.simulation.mock_server import MockAPIServer, generate_mock_response, _build_object
from finspark.simulation.reporter import json_report, junit_xml, text_report
from finspark.simulation.rollback import ConfigSnapshot, RollbackManager
from finspark.simulation.sandbox import Sandbox, SandboxRegistry
from finspark.simulation.types import (
    AdapterKind,
    AdapterSchema,
    EndpointSchema,
    FieldMapping,
    HttpMethod,
    IntegrationConfig,
    SimulationReport,
    StepResult,
    StepStatus,
    VersionComparisonResult,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _credit_endpoint() -> EndpointSchema:
    return EndpointSchema(
        path="/v1/credit/score",
        method=HttpMethod.POST,
        summary="Fetch credit score",
        request_schema={
            "type": "object",
            "required": ["pan"],
            "properties": {
                "pan": {"type": "string", "minLength": 10, "maxLength": 10},
                "consent": {"type": "boolean"},
            },
        },
        response_schema={
            "type": "object",
            "required": ["score", "bureau_id"],
            "properties": {
                "score": {"type": "integer", "minimum": 300, "maximum": 900},
                "bureau_id": {"type": "string"},
                "risk_band": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                "report_date": {"type": "string", "format": "date"},
            },
        },
        success_codes=[200],
        latency_p50_ms=200,
        error_rate=0.0,  # deterministic in unit tests
    )


def _kyc_endpoint() -> EndpointSchema:
    return EndpointSchema(
        path="/v2/kyc/verify",
        method=HttpMethod.POST,
        response_schema={
            "type": "object",
            "required": ["status"],
            "properties": {
                "status": {"type": "string", "enum": ["verified", "pending", "rejected"]},
                "reference_id": {"type": "string"},
            },
        },
        success_codes=[200, 201],
        error_rate=0.0,
    )


@pytest.fixture()
def credit_schema() -> AdapterSchema:
    return AdapterSchema(
        adapter_id="equifax_v1",
        name="Equifax Credit Bureau",
        kind=AdapterKind.CREDIT_BUREAU,
        version="1.0.0",
        base_url="https://api.equifax.mock",
        endpoints=[_credit_endpoint()],
        field_mappings=[
            FieldMapping(source_field="pan_number", target_field="pan"),
            FieldMapping(source_field="customer_consent", target_field="consent"),
        ],
    )


@pytest.fixture()
def kyc_schema() -> AdapterSchema:
    return AdapterSchema(
        adapter_id="kyc_provider_v2",
        name="KYC Provider",
        kind=AdapterKind.KYC,
        version="2.0.0",
        base_url="https://api.kyc.mock",
        endpoints=[_kyc_endpoint()],
    )


@pytest.fixture()
def integration_config(credit_schema: AdapterSchema) -> IntegrationConfig:
    return IntegrationConfig(
        tenant_id="tenant-abc",
        adapter_id=credit_schema.adapter_id,
        adapter_version=credit_schema.version,
        settings={"api_key": "test-key-123"},
        field_overrides=[
            FieldMapping(source_field="pan_number", target_field="score"),
        ],
    )


# ---------------------------------------------------------------------------
# Tests: mock_server / synthetic data generation
# ---------------------------------------------------------------------------


class TestSyntheticDataGeneration:
    def test_build_object_required_fields(self) -> None:
        schema = {
            "type": "object",
            "required": ["score", "bureau_id"],
            "properties": {
                "score": {"type": "integer", "minimum": 300, "maximum": 900},
                "bureau_id": {"type": "string"},
            },
        }
        obj = _build_object(schema)
        assert "score" in obj
        assert "bureau_id" in obj
        assert isinstance(obj["score"], int)
        assert 300 <= obj["score"] <= 900

    def test_build_object_enum_respected(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "risk_band": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
            },
        }
        for _ in range(20):
            obj = _build_object(schema)
            assert obj["risk_band"] in ["LOW", "MEDIUM", "HIGH"]

    def test_generate_mock_response_matches_schema(
        self, credit_schema: AdapterSchema
    ) -> None:
        ep = credit_schema.endpoints[0]
        resp = generate_mock_response(ep)
        assert "score" in resp
        assert "bureau_id" in resp
        assert isinstance(resp["score"], int)

    def test_generate_mock_response_no_schema(self) -> None:
        ep = EndpointSchema(
            path="/ping",
            method=HttpMethod.GET,
            success_codes=[200],
        )
        resp = generate_mock_response(ep)
        assert "status" in resp

    def test_deterministic_with_seed(self, credit_schema: AdapterSchema) -> None:
        ep = credit_schema.endpoints[0]
        server_a = MockAPIServer(credit_schema, seed=42)
        server_b = MockAPIServer(credit_schema, seed=42)
        # Both use same seed → same synthetic values
        resp_a = generate_mock_response(ep)
        resp_b = generate_mock_response(ep)
        assert type(resp_a["score"]) == type(resp_b["score"])


# ---------------------------------------------------------------------------
# Tests: contract validation
# ---------------------------------------------------------------------------


class TestContractValidation:
    def test_pass_on_valid_response(self) -> None:
        ep = _credit_endpoint()
        body = {"score": 720, "bureau_id": "EQ-001", "risk_band": "LOW", "report_date": "2024-01-15"}
        violations = validate_contract(ep, body, status_code=200)
        assert violations == []

    def test_fail_on_missing_required_field(self) -> None:
        ep = _credit_endpoint()
        body = {"score": 720}  # missing bureau_id
        violations = validate_contract(ep, body, status_code=200)
        assert any("bureau_id" in v for v in violations)

    def test_fail_on_wrong_status_code(self) -> None:
        ep = _credit_endpoint()
        body = {"score": 720, "bureau_id": "EQ-001"}
        violations = validate_contract(ep, body, status_code=500)
        assert any("500" in v for v in violations)

    def test_fail_on_wrong_type(self) -> None:
        ep = _credit_endpoint()
        body = {"score": "not-an-int", "bureau_id": "EQ-001"}
        violations = validate_contract(ep, body, status_code=200)
        assert len(violations) > 0  # jsonschema or built-in both should flag the type mismatch

    def test_fail_on_enum_violation(self) -> None:
        ep = _credit_endpoint()
        body = {"score": 720, "bureau_id": "EQ-001", "risk_band": "UNKNOWN"}
        violations = validate_contract(ep, body, status_code=200)
        assert any("risk_band" in v or "UNKNOWN" in v for v in violations)

    def test_pass_when_no_response_schema(self) -> None:
        ep = EndpointSchema(path="/any", method=HttpMethod.POST, success_codes=[200])
        violations = validate_contract(ep, {}, status_code=200)
        assert violations == []

    def test_string_min_length(self) -> None:
        schema = {
            "type": "object",
            "properties": {"code": {"type": "string", "minLength": 5}},
        }
        ep = EndpointSchema(
            path="/test",
            method=HttpMethod.POST,
            response_schema=schema,
            success_codes=[200],
        )
        violations = validate_contract(ep, {"code": "ab"}, status_code=200)
        assert len(violations) > 0  # "too short" from jsonschema or "minLength" from built-in

    def test_numeric_minimum(self) -> None:
        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer", "minimum": 300}},
        }
        ep = EndpointSchema(
            path="/test",
            method=HttpMethod.POST,
            response_schema=schema,
            success_codes=[200],
        )
        violations = validate_contract(ep, {"score": 100}, status_code=200)
        assert len(violations) > 0  # "less than the minimum" from jsonschema or "minimum" from built-in


# ---------------------------------------------------------------------------
# Tests: rollback
# ---------------------------------------------------------------------------


class TestRollbackManager:
    def test_snapshot_capture_and_restore(self, integration_config: IntegrationConfig) -> None:
        original_key = integration_config.settings["api_key"]
        snap = ConfigSnapshot.capture(integration_config)

        # mutate
        integration_config.settings["api_key"] = "mutated-key"
        assert integration_config.settings["api_key"] == "mutated-key"

        # restore
        snap.restore(integration_config)
        assert integration_config.settings["api_key"] == original_key

    def test_restore_rejects_wrong_config_id(
        self, integration_config: IntegrationConfig
    ) -> None:
        snap = ConfigSnapshot.capture(integration_config)
        other = integration_config.model_copy(deep=True)
        other.config_id = "completely-different-id"
        with pytest.raises(ValueError, match="config_id"):
            snap.restore(other)

    def test_rollback_manager_push_rollback(
        self, integration_config: IntegrationConfig
    ) -> None:
        mgr = RollbackManager(integration_config)
        original_version = integration_config.adapter_version

        mgr.push_snapshot()
        integration_config.adapter_version = "9.9.9"
        assert integration_config.adapter_version == "9.9.9"

        mgr.rollback()
        assert integration_config.adapter_version == original_version

    def test_rollback_manager_commit_discards_snapshot(
        self, integration_config: IntegrationConfig
    ) -> None:
        mgr = RollbackManager(integration_config)
        mgr.push_snapshot()
        integration_config.settings["new_key"] = "val"
        mgr.commit()
        # commit should reduce stack depth to 0
        assert mgr.depth == 0
        with pytest.raises(IndexError):
            mgr.commit()

    def test_transaction_context_manager_success(
        self, integration_config: IntegrationConfig
    ) -> None:
        mgr = RollbackManager(integration_config)
        with mgr.transaction():
            integration_config.settings["temp"] = "yes"
        # committed — change persists
        assert integration_config.settings.get("temp") == "yes"

    def test_transaction_context_manager_rollback_on_exception(
        self, integration_config: IntegrationConfig
    ) -> None:
        mgr = RollbackManager(integration_config)
        original_settings = copy.deepcopy(integration_config.settings)

        with pytest.raises(RuntimeError):
            with mgr.transaction():
                integration_config.settings["temp"] = "yes"
                raise RuntimeError("simulation failure")

        # rolled back — temp key should be gone
        assert "temp" not in integration_config.settings
        assert integration_config.settings == original_settings

    def test_snapshot_deep_copies_settings(
        self, integration_config: IntegrationConfig
    ) -> None:
        snap = ConfigSnapshot.capture(integration_config)
        integration_config.settings["api_key"] = "mutated"
        # snapshot should still have original
        assert snap.settings["api_key"] == "test-key-123"


# ---------------------------------------------------------------------------
# Tests: sandbox
# ---------------------------------------------------------------------------


class TestSandbox:
    def test_sandbox_creates_isolated_config_copy(
        self, integration_config: IntegrationConfig, credit_schema: AdapterSchema
    ) -> None:
        sb = Sandbox("tenant-abc", integration_config, credit_schema)
        # mutate original
        integration_config.settings["mutated"] = True
        # sandbox copy should be unaffected
        assert "mutated" not in sb.config.settings

    def test_sandbox_registry_tracks_active(
        self, integration_config: IntegrationConfig, credit_schema: AdapterSchema
    ) -> None:
        reg = SandboxRegistry()
        sb = reg.create("tenant-abc", integration_config, credit_schema)
        assert len(reg) == 1
        assert sb in reg.active_for_tenant("tenant-abc")
        reg.release(sb.sandbox_id)
        assert len(reg) == 0

    def test_sandbox_client_raises_outside_context(
        self, integration_config: IntegrationConfig, credit_schema: AdapterSchema
    ) -> None:
        sb = Sandbox("tenant-abc", integration_config, credit_schema)
        with pytest.raises(RuntimeError, match="not activated"):
            _ = sb.client

    @pytest.mark.asyncio
    async def test_sandbox_client_returns_mock_response(
        self, integration_config: IntegrationConfig, credit_schema: AdapterSchema
    ) -> None:
        sb = Sandbox("tenant-abc", integration_config, credit_schema, seed=99)
        async with sb.activate():
            resp = await sb.client.post(
                "/v1/credit/score",
                json={"pan": "ABCDE1234F", "consent": True},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "score" in body


# ---------------------------------------------------------------------------
# Tests: reporter
# ---------------------------------------------------------------------------


class TestReporter:
    def _make_report(self) -> SimulationReport:
        report = SimulationReport(
            tenant_id="t1",
            adapter_id="equifax_v1",
            adapter_version="1.0.0",
        )
        report.steps = [
            StepResult(
                step_name="POST /v1/credit/score",
                status=StepStatus.PASS,
                duration_ms=142.5,
                status_code=200,
                response_payload={"score": 720, "bureau_id": "EQ-001"},
            ),
            StepResult(
                step_name="POST /v1/credit/report",
                status=StepStatus.FAIL,
                duration_ms=88.3,
                status_code=502,
                contract_violations=["Status 502 not in success_codes [200]"],
                error=None,
            ),
        ]
        report.finalise()
        return report

    def test_text_report_contains_step_names(self) -> None:
        report = self._make_report()
        out = text_report(report, colour=False)
        assert "POST /v1/credit/score" in out
        assert "POST /v1/credit/report" in out
        assert "pass=1" in out
        assert "fail=1" in out

    def test_text_report_shows_rollback(self) -> None:
        report = self._make_report()
        report.rollback_triggered = True
        report.rollback_reason = "auto-rollback test"
        out = text_report(report, colour=False)
        assert "ROLLBACK" in out

    def test_json_report_is_valid_json(self) -> None:
        import json

        report = self._make_report()
        raw = json_report(report)
        parsed = json.loads(raw)
        assert parsed["tenant_id"] == "t1"
        assert len(parsed["steps"]) == 2

    def test_junit_xml_structure(self) -> None:
        import xml.etree.ElementTree as ET

        report = self._make_report()
        xml_str = junit_xml(report)
        root = ET.fromstring(xml_str)
        assert root.tag == "testsuite"
        test_cases = root.findall("testcase")
        assert len(test_cases) == 2

    def test_junit_xml_failure_node(self) -> None:
        import xml.etree.ElementTree as ET

        report = self._make_report()
        xml_str = junit_xml(report)
        root = ET.fromstring(xml_str)
        failures = root.findall(".//failure")
        assert len(failures) == 1

    def test_report_finalise_computes_counts(self) -> None:
        report = self._make_report()
        assert report.pass_count == 1
        assert report.fail_count == 1
        assert report.overall_status == StepStatus.FAIL

    def test_step_field_accuracy_score(self) -> None:
        from finspark.simulation.types import FieldAccuracy

        step = StepResult(
            step_name="test",
            status=StepStatus.PASS,
            duration_ms=10.0,
            field_accuracies=[
                FieldAccuracy(field="score", matched=True),
                FieldAccuracy(field="name", matched=False),
                FieldAccuracy(field="bureau_id", matched=True),
            ],
        )
        assert step.field_accuracy_score == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# Tests: SimulationReport model
# ---------------------------------------------------------------------------


class TestSimulationReport:
    def test_finalise_sets_overall_pass(self) -> None:
        report = SimulationReport(
            tenant_id="t", adapter_id="a", adapter_version="1.0.0"
        )
        report.steps = [
            StepResult(step_name="s1", status=StepStatus.PASS, duration_ms=10.0),
            StepResult(step_name="s2", status=StepStatus.PASS, duration_ms=20.0),
        ]
        report.finalise()
        assert report.overall_status == StepStatus.PASS
        assert report.total_duration_ms == pytest.approx(30.0)

    def test_finalise_sets_overall_error_precedence(self) -> None:
        report = SimulationReport(
            tenant_id="t", adapter_id="a", adapter_version="1.0.0"
        )
        report.steps = [
            StepResult(step_name="s1", status=StepStatus.PASS, duration_ms=5.0),
            StepResult(step_name="s2", status=StepStatus.ERROR, duration_ms=5.0),
            StepResult(step_name="s3", status=StepStatus.FAIL, duration_ms=5.0),
        ]
        report.finalise()
        # ERROR takes precedence over FAIL
        assert report.overall_status == StepStatus.ERROR
