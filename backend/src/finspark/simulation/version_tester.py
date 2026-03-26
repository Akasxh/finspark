"""
Parallel version tester — runs the same request against v1 and v2 adapters
simultaneously and compares results.

Produces VersionComparisonResult records that flag:
- Status code differences
- Response field divergence (present in one, missing in other)
- Field value type mismatches
- Latency delta
- Contract compliance per version
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog

from finspark.simulation.contract import validate_contract
from finspark.simulation.mock_server import MockAPIServer, generate_mock_response
from finspark.simulation.sandbox import Sandbox, SandboxRegistry
from finspark.simulation.types import (
    AdapterSchema,
    EndpointSchema,
    FieldAccuracy,
    IntegrationConfig,
    StepResult,
    StepStatus,
    VersionComparisonResult,
)

logger = structlog.get_logger(__name__)

_registry = SandboxRegistry()


class VersionTester:
    """
    Runs identical requests against two adapter versions in parallel.

    Parameters
    ----------
    config_v1   : IntegrationConfig for v1
    schema_v1   : AdapterSchema for v1
    config_v2   : IntegrationConfig for v2
    schema_v2   : AdapterSchema for v2
    payloads    : Per-path request payloads.  Both versions receive the same payload.
    seed        : RNG seed for deterministic mock responses (same seed → same bodies).
    """

    def __init__(
        self,
        config_v1: IntegrationConfig,
        schema_v1: AdapterSchema,
        config_v2: IntegrationConfig,
        schema_v2: AdapterSchema,
        *,
        payloads: dict[str, dict[str, Any]] | None = None,
        seed: int | None = None,
    ) -> None:
        self._cv1 = config_v1
        self._sv1 = schema_v1
        self._cv2 = config_v2
        self._sv2 = schema_v2
        self._payloads = payloads or {}
        self._seed = seed

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def compare_all(self) -> list[VersionComparisonResult]:
        """
        For every endpoint in v1, find the matching path in v2 and compare.
        Endpoints present in v1 but absent in v2 are flagged as breaking.
        Returns one VersionComparisonResult per endpoint.
        """
        # build v2 endpoint lookup
        v2_by_path: dict[str, EndpointSchema] = {ep.path: ep for ep in self._sv2.endpoints}

        sb_v1 = _registry.create(self._cv1.tenant_id, self._cv1, self._sv1, seed=self._seed)
        sb_v2 = _registry.create(self._cv2.tenant_id, self._cv2, self._sv2, seed=self._seed)

        results: list[VersionComparisonResult] = []

        async with sb_v1.activate(), sb_v2.activate():
            tasks = []
            for ep_v1 in self._sv1.endpoints:
                ep_v2 = v2_by_path.get(ep_v1.path)
                payload = self._payloads.get(ep_v1.path) or {}
                tasks.append(
                    self._compare_endpoint(sb_v1, sb_v2, ep_v1, ep_v2, payload)
                )
            results = list(await asyncio.gather(*tasks))

        _registry.release(sb_v1.sandbox_id)
        _registry.release(sb_v2.sandbox_id)
        return results

    # ------------------------------------------------------------------
    # Per-endpoint comparison
    # ------------------------------------------------------------------

    async def _compare_endpoint(
        self,
        sb_v1: Sandbox,
        sb_v2: Sandbox,
        ep_v1: EndpointSchema,
        ep_v2: EndpointSchema | None,
        payload: dict[str, Any],
    ) -> VersionComparisonResult:
        step_name = f"{ep_v1.method.value} {ep_v1.path}"

        # --- missing in v2: immediate breaking change -------------------
        if ep_v2 is None:
            missing_step = StepResult(
                step_name=step_name,
                status=StepStatus.FAIL,
                duration_ms=0.0,
                error=f"Endpoint '{ep_v1.path}' missing in v2 schema",
            )
            v1_step = await self._call_endpoint(sb_v1, ep_v1, payload)
            return VersionComparisonResult(
                request_payload=payload,
                v1_step=v1_step,
                v2_step=missing_step,
                compatible=False,
                notes=[f"Breaking: '{ep_v1.path}' not found in v2"],
            )

        # --- parallel calls ---------------------------------------------
        v1_step, v2_step = await asyncio.gather(
            self._call_endpoint(sb_v1, ep_v1, payload),
            self._call_endpoint(sb_v2, ep_v2, payload),
        )

        # --- diff -------------------------------------------------------
        diverged, notes, compatible = self._diff_responses(
            ep_v1, ep_v2, v1_step, v2_step
        )

        return VersionComparisonResult(
            request_payload=payload,
            v1_step=v1_step,
            v2_step=v2_step,
            fields_diverged=diverged,
            latency_delta_ms=v2_step.duration_ms - v1_step.duration_ms,
            compatible=compatible,
            notes=notes,
        )

    # ------------------------------------------------------------------

    @staticmethod
    async def _call_endpoint(
        sb: Sandbox,
        ep: EndpointSchema,
        payload: dict[str, Any],
    ) -> StepResult:
        step_name = f"{ep.method.value} {ep.path}"
        t0 = time.perf_counter()
        status_code: int | None = None
        response_body: dict[str, Any] = {}
        error_msg: str | None = None

        try:
            resp = await sb.client.request(
                method=ep.method.value,
                url=ep.path,
                json=payload,
            )
            status_code = resp.status_code
            try:
                response_body = resp.json()
            except Exception:
                response_body = {"_raw": resp.text}
        except httpx.HTTPError as exc:
            error_msg = str(exc)
        except Exception as exc:
            error_msg = f"Unexpected: {exc}"

        duration_ms = (time.perf_counter() - t0) * 1000.0
        violations: list[str] = []
        if error_msg is None and status_code is not None:
            violations = validate_contract(ep, response_body, status_code)

        if error_msg:
            status = StepStatus.ERROR
        elif violations or status_code not in ep.success_codes:
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
            contract_violations=violations,
            error=error_msg,
        )

    @staticmethod
    def _diff_responses(
        ep_v1: EndpointSchema,
        ep_v2: EndpointSchema,
        r1: StepResult,
        r2: StepResult,
    ) -> tuple[list[str], list[str], bool]:
        """
        Returns (diverged_fields, notes, is_compatible).
        Compatible = same status class AND no removed response fields.
        """
        notes: list[str] = []
        diverged: list[str] = []

        body1 = _flatten(r1.response_payload or {})
        body2 = _flatten(r2.response_payload or {})

        # fields present in v1 but missing in v2 → breaking
        removed = set(body1) - set(body2)
        for f in removed:
            diverged.append(f)
            notes.append(f"Breaking: field '{f}' present in v1, absent in v2")

        # new fields in v2 are additive — not breaking
        added = set(body2) - set(body1)
        for f in added:
            notes.append(f"Additive: new field '{f}' in v2")

        # type mismatches on shared fields
        for f in set(body1) & set(body2):
            if type(body1[f]) != type(body2[f]):
                diverged.append(f)
                notes.append(
                    f"Type change: '{f}' is {type(body1[f]).__name__} in v1, "
                    f"{type(body2[f]).__name__} in v2"
                )

        # status code class comparison
        sc1 = r1.status_code or 0
        sc2 = r2.status_code or 0
        if (sc1 // 100) != (sc2 // 100):
            notes.append(f"Status class mismatch: v1={sc1} v2={sc2}")
            diverged.append("_status_code")

        compatible = len(removed) == 0 and "_status_code" not in diverged
        return diverged, notes, compatible


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested dict to dot-notation keys."""
    result: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        else:
            result[key] = v
    return result
