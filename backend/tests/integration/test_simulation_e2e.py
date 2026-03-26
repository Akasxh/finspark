"""
End-to-end integration tests for Module 4 — Simulation & Testing Framework.

These tests exercise the full async pipeline:
  IntegrationSimulator.run() → sandbox → mock transport → contract validation
  VersionTester.compare_all() → parallel v1/v2 sandboxes → diff

No database; no real network. All HTTP is intercepted by the sandbox transport.

Marks:
    integration — all tests here
"""
from __future__ import annotations

from typing import Any

import pytest

from finspark.simulation import (
    IntegrationSimulator,
    VersionTester,
    json_report,
    junit_xml,
    print_report,
    text_report,
    version_comparison_text,
)
from finspark.simulation.types import (
    AdapterKind,
    AdapterSchema,
    EndpointSchema,
    FieldMapping,
    HttpMethod,
    IntegrationConfig,
    StepStatus,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_cibil_schema(version: str = "1.0.0") -> AdapterSchema:
    return AdapterSchema(
        adapter_id=f"cibil_{version.replace('.', '_')}",
        name="CIBIL Credit Bureau",
        kind=AdapterKind.CREDIT_BUREAU,
        version=version,
        base_url="https://api.cibil.mock",
        endpoints=[
            EndpointSchema(
                path="/v1/score",
                method=HttpMethod.POST,
                summary="Fetch CIBIL score",
                request_schema={
                    "type": "object",
                    "required": ["pan"],
                    "properties": {
                        "pan": {"type": "string"},
                        "date_of_birth": {"type": "string", "format": "date"},
                    },
                },
                response_schema={
                    "type": "object",
                    "required": ["score", "member_id"],
                    "properties": {
                        "score": {"type": "integer", "minimum": 300, "maximum": 900},
                        "member_id": {"type": "string"},
                        "enquiry_date": {"type": "string", "format": "date"},
                        "risk_category": {
                            "type": "string",
                            "enum": ["EXCELLENT", "GOOD", "FAIR", "POOR"],
                        },
                    },
                },
                success_codes=[200],
                error_rate=0.0,
            ),
            EndpointSchema(
                path="/v1/report",
                method=HttpMethod.GET,
                summary="Fetch full credit report",
                response_schema={
                    "type": "object",
                    "required": ["report_id"],
                    "properties": {
                        "report_id": {"type": "string"},
                        "accounts": {"type": "array", "items": {"type": "object"}},
                    },
                },
                success_codes=[200],
                error_rate=0.0,
            ),
        ],
        field_mappings=[
            FieldMapping(source_field="pan_number", target_field="pan"),
        ],
    )


def _make_cibil_v2_schema() -> AdapterSchema:
    """v2 adds a new field, renames risk_category → risk_band (breaking)."""
    return AdapterSchema(
        adapter_id="cibil_v2",
        name="CIBIL Credit Bureau v2",
        kind=AdapterKind.CREDIT_BUREAU,
        version="2.0.0",
        base_url="https://api.cibil-v2.mock",
        endpoints=[
            EndpointSchema(
                path="/v1/score",
                method=HttpMethod.POST,
                response_schema={
                    "type": "object",
                    "required": ["score", "member_id"],
                    "properties": {
                        "score": {"type": "integer", "minimum": 300, "maximum": 900},
                        "member_id": {"type": "string"},
                        "risk_band": {         # renamed from risk_category
                            "type": "string",
                            "enum": ["EXCELLENT", "GOOD", "FAIR", "POOR"],
                        },
                        "new_field": {"type": "string"},  # additive
                    },
                },
                success_codes=[200],
                error_rate=0.0,
            ),
            # /v1/report is intentionally absent → breaking removal
        ],
    )


@pytest.fixture()
def cibil_config() -> IntegrationConfig:
    return IntegrationConfig(
        tenant_id="tenant-finbank",
        adapter_id="cibil_1_0_0",
        adapter_version="1.0.0",
        settings={"api_key": "cibil-key-abc"},
        field_overrides=[
            FieldMapping(source_field="pan_number", target_field="score"),
            FieldMapping(source_field="customer_dob", target_field="enquiry_date"),
        ],
    )


# ---------------------------------------------------------------------------
# Integration tests: IntegrationSimulator
# ---------------------------------------------------------------------------


class TestIntegrationSimulatorE2E:
    @pytest.mark.asyncio
    async def test_full_simulation_all_pass(self, cibil_config: IntegrationConfig) -> None:
        schema = _make_cibil_schema("1.0.0")
        sim = IntegrationSimulator(
            cibil_config,
            schema,
            seed=42,
        )
        report = await sim.run()

        assert report.overall_status == StepStatus.PASS
        assert report.pass_count == 2
        assert report.fail_count == 0
        assert report.error_count == 0
        assert report.total_duration_ms >= 0
        assert report.sandbox_id is not None
        assert not report.rollback_triggered

    @pytest.mark.asyncio
    async def test_simulation_triggers_rollback_on_error(
        self, cibil_config: IntegrationConfig
    ) -> None:
        schema = _make_cibil_schema("1.0.0")
        # force 100% error rate → all steps fail → rollback triggered
        original_version = cibil_config.adapter_version
        sim = IntegrationSimulator(
            cibil_config,
            schema,
            seed=1,
            force_error_rate=1.0,
            auto_rollback=True,
        )
        report = await sim.run()

        # all steps fail due to 502 from mock server
        assert report.fail_count > 0 or report.error_count > 0
        assert report.rollback_triggered
        # config must be restored
        assert cibil_config.adapter_version == original_version

    @pytest.mark.asyncio
    async def test_simulation_no_rollback_when_disabled(
        self, cibil_config: IntegrationConfig
    ) -> None:
        schema = _make_cibil_schema("1.0.0")
        cibil_config.adapter_version = "mutated-during-test"

        sim = IntegrationSimulator(
            cibil_config,
            schema,
            seed=1,
            force_error_rate=1.0,
            auto_rollback=False,
        )
        report = await sim.run()
        assert not report.rollback_triggered

    @pytest.mark.asyncio
    async def test_report_field_accuracy_populated(
        self, cibil_config: IntegrationConfig
    ) -> None:
        schema = _make_cibil_schema("1.0.0")
        sim = IntegrationSimulator(cibil_config, schema, seed=7)
        report = await sim.run()
        # field_overrides has 2 entries → field_accuracies should be populated
        steps_with_fa = [s for s in report.steps if s.field_accuracies]
        assert len(steps_with_fa) > 0

    @pytest.mark.asyncio
    async def test_report_text_output(self, cibil_config: IntegrationConfig) -> None:
        schema = _make_cibil_schema("1.0.0")
        sim = IntegrationSimulator(cibil_config, schema, seed=0)
        report = await sim.run()
        out = text_report(report, colour=False)
        assert "PASS" in out or "FAIL" in out or "ERROR" in out
        assert report.adapter_id in out

    @pytest.mark.asyncio
    async def test_report_json_serialisable(self, cibil_config: IntegrationConfig) -> None:
        import json

        schema = _make_cibil_schema("1.0.0")
        sim = IntegrationSimulator(cibil_config, schema, seed=0)
        report = await sim.run()
        raw = json_report(report)
        parsed = json.loads(raw)
        assert parsed["tenant_id"] == "tenant-finbank"

    @pytest.mark.asyncio
    async def test_report_junit_xml(self, cibil_config: IntegrationConfig) -> None:
        import xml.etree.ElementTree as ET

        schema = _make_cibil_schema("1.0.0")
        sim = IntegrationSimulator(cibil_config, schema, seed=0)
        report = await sim.run()
        xml_str = junit_xml(report)
        root = ET.fromstring(xml_str)
        assert root.tag == "testsuite"
        assert int(root.attrib["tests"]) == len(report.steps)

    @pytest.mark.asyncio
    async def test_custom_payloads_used(self, cibil_config: IntegrationConfig) -> None:
        schema = _make_cibil_schema("1.0.0")
        custom_payload: dict[str, Any] = {"pan": "ABCDE1234F", "date_of_birth": "1985-06-15"}
        sim = IntegrationSimulator(
            cibil_config,
            schema,
            payloads={"/v1/score": custom_payload},
            seed=5,
        )
        report = await sim.run()
        score_step = next(s for s in report.steps if "score" in s.step_name)
        assert score_step.request_payload == custom_payload

    @pytest.mark.asyncio
    async def test_skipped_steps_after_failure(
        self, cibil_config: IntegrationConfig
    ) -> None:
        schema = _make_cibil_schema("1.0.0")
        # override error rate: only first endpoint fails
        ep_fail = EndpointSchema(
            path="/v1/score",
            method=HttpMethod.POST,
            response_schema=schema.endpoints[0].response_schema,
            success_codes=[200],
            error_rate=1.0,  # always error
        )
        ep_pass = schema.endpoints[1]
        failing_schema = AdapterSchema(
            adapter_id="cibil_partial_fail",
            name="CIBIL partial fail",
            kind=AdapterKind.CREDIT_BUREAU,
            version="1.0.0",
            base_url="https://api.cibil.mock",
            endpoints=[ep_fail, ep_pass],
        )
        sim = IntegrationSimulator(cibil_config, failing_schema, seed=1, auto_rollback=True)
        report = await sim.run()
        # second step should be skipped after first failure
        second_step = report.steps[1]
        assert second_step.status == StepStatus.SKIP


# ---------------------------------------------------------------------------
# Integration tests: VersionTester
# ---------------------------------------------------------------------------


class TestVersionTesterE2E:
    @pytest.mark.asyncio
    async def test_compare_detects_additive_field(self) -> None:
        """
        v2 is a strict superset of v1 (all v1 fields preserved, one new field added).
        The result should be compatible with an 'Additive' note.
        """
        # v1 schema: score + member_id only
        schema_v1 = AdapterSchema(
            adapter_id="cibil_v1_minimal",
            name="CIBIL v1 minimal",
            kind=AdapterKind.CREDIT_BUREAU,
            version="1.0.0",
            base_url="https://api.cibil.mock",
            endpoints=[
                EndpointSchema(
                    path="/v1/score",
                    method=HttpMethod.POST,
                    response_schema={
                        "type": "object",
                        "required": ["score", "member_id"],
                        "properties": {
                            "score": {"type": "integer", "minimum": 300, "maximum": 900},
                            "member_id": {"type": "string"},
                        },
                    },
                    success_codes=[200],
                    error_rate=0.0,
                ),
            ],
        )
        # v2 schema: same fields + one additive new_field
        schema_v2 = AdapterSchema(
            adapter_id="cibil_v2_additive",
            name="CIBIL v2 additive",
            kind=AdapterKind.CREDIT_BUREAU,
            version="2.0.0",
            base_url="https://api.cibil-v2.mock",
            endpoints=[
                EndpointSchema(
                    path="/v1/score",
                    method=HttpMethod.POST,
                    response_schema={
                        "type": "object",
                        "required": ["score", "member_id"],
                        "properties": {
                            "score": {"type": "integer", "minimum": 300, "maximum": 900},
                            "member_id": {"type": "string"},
                            "new_field": {"type": "string"},  # additive only
                        },
                    },
                    success_codes=[200],
                    error_rate=0.0,
                ),
            ],
        )
        config_v1 = IntegrationConfig(
            tenant_id="t", adapter_id="cibil_v1", adapter_version="1.0.0",
            settings={"api_key": "k"},
        )
        config_v2 = IntegrationConfig(
            tenant_id="t", adapter_id="cibil_v2", adapter_version="2.0.0",
            settings={"api_key": "k"},
        )
        tester = VersionTester(config_v1, schema_v1, config_v2, schema_v2, seed=3)
        results = await tester.compare_all()

        assert len(results) == 1
        score_result = results[0]
        # compatible: no v1 fields removed
        assert score_result.compatible
        # additive note present
        assert any("Additive" in n or "new_field" in n for n in score_result.notes)

    @pytest.mark.asyncio
    async def test_compare_detects_breaking_removal(self) -> None:
        schema_v1 = _make_cibil_schema("1.0.0")
        schema_v2 = _make_cibil_v2_schema()

        config_v1 = IntegrationConfig(
            tenant_id="t", adapter_id="cibil_v1", adapter_version="1.0.0",
            settings={"api_key": "k"},
        )
        config_v2 = IntegrationConfig(
            tenant_id="t", adapter_id="cibil_v2", adapter_version="2.0.0",
            settings={"api_key": "k"},
        )
        tester = VersionTester(config_v1, schema_v1, config_v2, schema_v2, seed=5)
        results = await tester.compare_all()

        # /v1/report is absent in v2 → breaking
        report_result = next(
            (r for r in results if "/v1/report" in r.v1_step.step_name), None
        )
        assert report_result is not None
        assert not report_result.compatible
        assert any("report" in n.lower() or "missing" in n.lower() for n in report_result.notes)

    @pytest.mark.asyncio
    async def test_version_comparison_text_output(self) -> None:
        schema_v1 = _make_cibil_schema("1.0.0")
        schema_v2 = _make_cibil_schema("2.0.0")  # identical schema, no breakage
        schema_v2.adapter_id = "cibil_2_0_0"
        schema_v2.version = "2.0.0"

        config_v1 = IntegrationConfig(
            tenant_id="t", adapter_id="cibil_v1", adapter_version="1.0.0",
            settings={"api_key": "k"},
        )
        config_v2 = IntegrationConfig(
            tenant_id="t", adapter_id="cibil_v2", adapter_version="2.0.0",
            settings={"api_key": "k"},
        )
        tester = VersionTester(config_v1, schema_v1, config_v2, schema_v2, seed=1)
        results = await tester.compare_all()

        for result in results:
            out = version_comparison_text(result, colour=False)
            assert "Version Comparison" in out
            assert "Compatibility" in out

    @pytest.mark.asyncio
    async def test_latency_delta_is_float(self) -> None:
        schema_v1 = _make_cibil_schema("1.0.0")
        schema_v2 = _make_cibil_schema("1.0.0")
        schema_v2.adapter_id = "cibil_same_v2"

        cfg_v1 = IntegrationConfig(
            tenant_id="t", adapter_id="a1", adapter_version="1.0.0", settings={}
        )
        cfg_v2 = IntegrationConfig(
            tenant_id="t", adapter_id="a2", adapter_version="1.0.0", settings={}
        )
        tester = VersionTester(cfg_v1, schema_v1, cfg_v2, schema_v2, seed=0)
        results = await tester.compare_all()
        for r in results:
            assert isinstance(r.latency_delta_ms, float)


# ---------------------------------------------------------------------------
# Integration tests: Multi-tenant sandbox isolation
# ---------------------------------------------------------------------------


class TestMultiTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenants_get_independent_sandboxes(self) -> None:
        schema = _make_cibil_schema("1.0.0")

        config_t1 = IntegrationConfig(
            tenant_id="tenant-alpha",
            adapter_id="cibil_1_0_0",
            adapter_version="1.0.0",
            settings={"api_key": "alpha-key"},
        )
        config_t2 = IntegrationConfig(
            tenant_id="tenant-beta",
            adapter_id="cibil_1_0_0",
            adapter_version="1.0.0",
            settings={"api_key": "beta-key"},
        )

        sim_t1 = IntegrationSimulator(config_t1, schema, seed=10)
        sim_t2 = IntegrationSimulator(config_t2, schema, seed=20)

        report_t1, report_t2 = await __import__("asyncio").gather(
            sim_t1.run(), sim_t2.run()
        )

        # Each tenant gets its own report / sandbox
        assert report_t1.tenant_id == "tenant-alpha"
        assert report_t2.tenant_id == "tenant-beta"
        assert report_t1.sandbox_id != report_t2.sandbox_id
        assert report_t1.run_id != report_t2.run_id

    @pytest.mark.asyncio
    async def test_config_mutation_in_one_tenant_does_not_affect_other(self) -> None:
        schema = _make_cibil_schema("1.0.0")

        config_original = IntegrationConfig(
            tenant_id="tenant-x",
            adapter_id="cibil_1_0_0",
            adapter_version="1.0.0",
            settings={"api_key": "original-key"},
        )

        # IntegrationSimulator deep-copies via Sandbox internally
        sim = IntegrationSimulator(config_original, schema, seed=0)
        await sim.run()

        # original config should be untouched (committed, no mutation)
        assert config_original.settings["api_key"] == "original-key"
