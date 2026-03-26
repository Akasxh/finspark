"""
IntegrationSimulator — end-to-end simulation driver.

Runs a configured integration against its MockAPIServer within a Sandbox,
collecting StepResults along the way.  On failure it can trigger rollback.

One simulator instance = one simulation run = one SimulationReport.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from finspark.simulation.contract import validate_contract
from finspark.simulation.mock_server import generate_mock_response
from finspark.simulation.rollback import RollbackManager
from finspark.simulation.sandbox import Sandbox, SandboxRegistry
from finspark.simulation.types import (
    AdapterSchema,
    FieldAccuracy,
    IntegrationConfig,
    SimulationReport,
    StepResult,
    StepStatus,
)

logger = structlog.get_logger(__name__)

_registry = SandboxRegistry()


class IntegrationSimulator:
    """
    Orchestrates a full integration simulation for a single tenant + adapter.

    Parameters
    ----------
    config  : IntegrationConfig  (will be snapshot-ed before any mutations)
    schema  : AdapterSchema
    payloads: Optional per-endpoint request payloads.  If omitted, the
              simulator auto-generates payloads from the request_schema.
    auto_rollback: Roll back config on any FAIL/ERROR step (default True).
    seed    : RNG seed for deterministic mock responses in CI.
    """

    def __init__(
        self,
        config: IntegrationConfig,
        schema: AdapterSchema,
        *,
        payloads: dict[str, dict[str, Any]] | None = None,
        auto_rollback: bool = True,
        seed: int | None = None,
        force_error_rate: float | None = None,
    ) -> None:
        self._config = config
        self._schema = schema
        self._payloads = payloads or {}
        self._auto_rollback = auto_rollback
        self._seed = seed
        self._force_error_rate = force_error_rate
        self._rollback_mgr = RollbackManager(config)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(self) -> SimulationReport:
        """
        Execute the simulation.  Returns a finalised SimulationReport.
        Never raises — all exceptions are captured into StepResult.error.
        """
        report = SimulationReport(
            tenant_id=self._config.tenant_id,
            adapter_id=self._config.adapter_id,
            adapter_version=self._config.adapter_version,
        )

        sandbox = _registry.create(
            self._config.tenant_id,
            self._config,
            self._schema,
            seed=self._seed,
            force_error_rate=self._force_error_rate,
        )
        report.sandbox_id = sandbox.sandbox_id

        logger.info(
            "simulation.start",
            run_id=report.run_id,
            tenant=self._config.tenant_id,
            adapter=self._config.adapter_id,
            version=self._config.adapter_version,
            sandbox=sandbox.sandbox_id,
        )

        # snapshot config before any steps that might mutate it
        self._rollback_mgr.push_snapshot()

        abort = False
        async with sandbox.activate():
            for endpoint in self._schema.endpoints:
                if abort:
                    report.steps.append(
                        StepResult(
                            step_name=f"{endpoint.method.value} {endpoint.path}",
                            status=StepStatus.SKIP,
                            duration_ms=0.0,
                        )
                    )
                    continue

                step = await self._run_step(sandbox, endpoint)
                report.steps.append(step)

                if step.status in (StepStatus.FAIL, StepStatus.ERROR):
                    if self._auto_rollback:
                        abort = True

        # trigger rollback if any step failed
        has_failure = any(
            s.status in (StepStatus.FAIL, StepStatus.ERROR) for s in report.steps
        )
        if has_failure and self._auto_rollback:
            snap = self._rollback_mgr.rollback()
            report.rollback_triggered = True
            report.rollback_reason = (
                f"Auto-rollback to snapshot {snap.snapshot_id} after step failure"
            )
            logger.warning(
                "simulation.rollback",
                run_id=report.run_id,
                snapshot_id=snap.snapshot_id,
            )
        else:
            self._rollback_mgr.commit()

        _registry.release(sandbox.sandbox_id)
        report.finalise()

        logger.info(
            "simulation.complete",
            run_id=report.run_id,
            status=report.overall_status,
            pass_count=report.pass_count,
            fail_count=report.fail_count,
            duration_ms=report.total_duration_ms,
        )
        return report

    # ------------------------------------------------------------------
    # Per-step execution
    # ------------------------------------------------------------------

    async def _run_step(self, sandbox: Sandbox, endpoint: "AdapterSchema.endpoints[0]") -> StepResult:  # type: ignore[index]
        from finspark.simulation.types import EndpointSchema

        if not isinstance(endpoint, EndpointSchema):  # guard
            raise TypeError(f"Expected EndpointSchema, got {type(endpoint)}")

        step_name = f"{endpoint.method.value} {endpoint.path}"
        payload = self._payloads.get(endpoint.path) or self._build_payload(endpoint)

        t0 = time.perf_counter()
        status_code: int | None = None
        response_body: dict[str, Any] = {}
        error_msg: str | None = None

        try:
            resp = await sandbox.client.request(
                method=endpoint.method.value,
                url=endpoint.path,
                json=payload,
                headers=self._auth_headers(sandbox.config),
            )
            status_code = resp.status_code
            try:
                response_body = resp.json()
            except Exception:
                response_body = {"_raw": resp.text}

        except httpx.HTTPError as exc:
            error_msg = f"HTTP error: {exc}"
        except Exception as exc:
            error_msg = f"Unexpected error: {exc}"

        duration_ms = (time.perf_counter() - t0) * 1000.0

        # contract validation
        violations: list[str] = []
        if error_msg is None and status_code is not None:
            violations = validate_contract(endpoint, response_body, status_code)

        # field mapping accuracy
        field_accuracies = self._check_field_accuracies(
            endpoint, response_body, sandbox.config
        )

        # determine step status
        if error_msg:
            status = StepStatus.ERROR
        elif violations or (status_code not in (endpoint.success_codes or [200, 201])):
            status = StepStatus.FAIL
        else:
            status = StepStatus.PASS

        return StepResult(
            step_name=step_name,
            status=status,
            duration_ms=duration_ms,
            request_payload=payload,
            response_payload=response_body,
            status_code=status_code,
            field_accuracies=field_accuracies,
            contract_violations=violations,
            error=error_msg,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_payload(endpoint: Any) -> dict[str, Any]:
        """Auto-generate a request payload from the endpoint's request_schema."""
        from finspark.simulation.mock_server import _build_object

        schema = endpoint.request_schema
        if schema and schema.get("type") == "object":
            return _build_object(schema)
        return {}

    @staticmethod
    def _auth_headers(config: IntegrationConfig) -> dict[str, str]:
        token = config.settings.get("api_key") or config.settings.get("token", "mock-token")
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _check_field_accuracies(
        endpoint: Any,
        response_body: dict[str, Any],
        config: IntegrationConfig,
    ) -> list[FieldAccuracy]:
        """
        For each configured field_override mapping verify the response
        contains the expected target field.  Returns FieldAccuracy records.
        """
        results: list[FieldAccuracy] = []
        all_mappings = list(config.field_overrides)

        for mapping in all_mappings:
            target = mapping.target_field
            # check if the target field appears somewhere in the flat response
            actual_val = _deep_get(response_body, target)
            matched = actual_val is not None
            results.append(
                FieldAccuracy(
                    field=target,
                    expected=mapping.source_field,
                    actual=actual_val,
                    matched=matched,
                    note="field present in response" if matched else "field missing from response",
                )
            )
        return results


def _deep_get(d: dict[str, Any], key: str) -> Any:
    """Traverse nested dict using dot-notation key, e.g. 'data.customer.name'."""
    parts = key.split(".")
    cur: Any = d
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur
