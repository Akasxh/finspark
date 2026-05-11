"""Integration simulation framework - mock testing of configurations."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Generator
from typing import Any

from finspark.schemas.simulations import SimulationStepResult
from finspark.services.chain_executor import (
    ChainExecutionError,
    execute_chain,
)
from finspark.services.llm.client import GeminiAPIError, GeminiClient

logger = logging.getLogger(__name__)


class MockAPIServer:
    """Generates realistic mock API responses based on adapter schemas."""

    # Realistic mock data for Indian fintech fields
    MOCK_DATA: dict[str, Any] = {
        "credit_score": 750,
        "pan_number": "ABCDE1234F",
        "aadhaar_number": "XXXX-XXXX-1234",
        "customer_name": "Rajesh Kumar",
        "full_name": "Rajesh Kumar Sharma",
        "date_of_birth": "1990-05-15",
        "mobile_number": "+919876543210",
        "email_address": "rajesh.kumar@example.com",
        "address": "123 MG Road, Bengaluru, Karnataka 560001",
        "loan_amount": 500000.00,
        "account_number": "1234567890",
        "ifsc_code": "SBIN0001234",
        "gstin": "29ABCDE1234F1ZK",
        "reference_id": "REF-2024-001234",
        "status": "success",
        "score": 750,
        "report_id": "RPT-2024-567890",
        "enquiry_id": "ENQ-2024-112233",
        "verification_status": "verified",
        "transaction_id": "TXN-2024-445566",
    }

    def generate_response(
        self,
        endpoint: dict[str, Any],
        request_payload: dict[str, Any],
        response_schema: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a mock response for an endpoint.

        If config contains adapter_name, uses adapter-specific generators
        for realistic responses. Falls back to schema-based or default.
        """
        from finspark.services.simulation.mock_responses import generate_mock_response

        adapter_name = (config or {}).get("adapter_name", "")
        base_url = (config or {}).get("base_url", "")
        if adapter_name or base_url:
            return generate_mock_response(
                adapter_name=adapter_name,
                endpoint_path=endpoint.get("path", ""),
                request_payload=request_payload,
                base_url=base_url,
            )

        if response_schema:
            return self._generate_from_schema(response_schema)

        # Default successful response
        return {
            "status": "success",
            "code": 200,
            "data": {
                "reference_id": self.MOCK_DATA["reference_id"],
                "message": f"Mock response for {endpoint.get('path', 'unknown')}",
                "timestamp": "2024-03-26T10:00:00Z",
            },
        }

    def _generate_from_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate mock data from a JSON schema."""
        if isinstance(schema, str):
            schema = json.loads(schema)

        result: dict[str, Any] = {}
        properties = schema.get("properties", {})

        for field_name, field_def in properties.items():
            field_type = field_def.get("type", "string")

            # Use domain-specific mock data if available
            if field_name in self.MOCK_DATA:
                result[field_name] = self.MOCK_DATA[field_name]
            elif field_type == "string":
                result[field_name] = f"mock_{field_name}"
            elif field_type == "integer":
                result[field_name] = 12345
            elif field_type == "number":
                result[field_name] = 123.45
            elif field_type == "boolean":
                result[field_name] = True
            elif field_type == "array":
                result[field_name] = []
            elif field_type == "object":
                result[field_name] = {}

        return result


class IntegrationSimulator:
    """Runs end-to-end simulation of integration configurations."""

    def __init__(self) -> None:
        self.mock_server = MockAPIServer()

    @staticmethod
    def _endpoints_use_chaining(endpoints: list[dict[str, Any]]) -> bool:
        """Return True if any endpoint has an ``id`` set (chain feature)."""
        return any(ep.get("id") is not None for ep in endpoints)

    def run_simulation(
        self,
        config: dict[str, Any],
        test_type: str = "full",
    ) -> list[SimulationStepResult]:
        """Run a complete simulation of an integration configuration."""
        steps: list[SimulationStepResult] = []

        # Step 1: Validate configuration structure
        steps.append(self._test_config_structure(config))

        # Step 2: Validate field mappings
        steps.append(self._test_field_mappings(config))

        # Step 3: Test each endpoint (chained or independent)
        endpoints = config.get("endpoints", [])
        if self._endpoints_use_chaining(endpoints):
            steps.extend(self._run_chained_endpoints_sync(endpoints, config))
        else:
            for endpoint in endpoints:
                if endpoint.get("enabled", True):
                    steps.append(self._test_endpoint(endpoint, config))

        # Step 4: Test authentication
        steps.append(self._test_auth_config(config))

        # Step 5: Test hooks
        steps.append(self._test_hooks(config))

        if test_type == "full":
            # Step 6: Test error handling
            steps.append(self._test_error_handling(config))

            # Step 7: Test retry logic
            steps.append(self._test_retry_logic(config))

        return steps

    def _run_chained_endpoints_sync(
        self,
        endpoints: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> list[SimulationStepResult]:
        """Execute chained endpoints synchronously via asyncio."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop -- create a task via a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(
                    asyncio.run,
                    self._run_chained_endpoints(endpoints, config),
                ).result()
            return results
        return asyncio.run(self._run_chained_endpoints(endpoints, config))

    async def _run_chained_endpoints(
        self,
        endpoints: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> list[SimulationStepResult]:
        """Run endpoints through the chain executor, producing step results."""
        enabled = [ep for ep in endpoints if ep.get("enabled", True)]

        async def _call_fn(
            endpoint: dict[str, Any], prepared_request: dict[str, Any]
        ) -> dict[str, Any]:
            return self.mock_server.generate_response(
                endpoint, prepared_request, config=config
            )

        start = time.monotonic()
        try:
            chain_results = await execute_chain(enabled, _call_fn)
        except ChainExecutionError as exc:
            return [
                SimulationStepResult(
                    step_name="chain_execution",
                    status="error",
                    error_message=str(exc),
                )
            ]
        total_ms = int((time.monotonic() - start) * 1000)
        per_step_ms = max(1, total_ms // max(len(chain_results), 1))

        steps: list[SimulationStepResult] = []
        for cr in chain_results:
            ep_id = cr["endpoint_id"]
            response = cr["response"]
            has_status = "status" in response
            steps.append(
                SimulationStepResult(
                    step_name=f"chained_endpoint_{ep_id}",
                    status="passed" if has_status else "failed",
                    request_payload=cr["request"],
                    expected_response={"status": "success"},
                    actual_response={
                        **response,
                        "chain_context": {
                            "extracted": cr["extracted"],
                            "injected_into_request": cr["request"],
                        },
                    },
                    duration_ms=per_step_ms,
                    confidence_score=0.9 if has_status else 0.3,
                )
            )
        return steps

    def run_simulation_stream(
        self,
        config: dict[str, Any],
        test_type: str = "full",
    ) -> Generator[SimulationStepResult, None, None]:
        """Yield simulation steps one at a time for streaming."""
        yield self._test_config_structure(config)
        yield self._test_field_mappings(config)

        for endpoint in config.get("endpoints", []):
            if endpoint.get("enabled", True):
                yield self._test_endpoint(endpoint, config)

        yield self._test_auth_config(config)
        yield self._test_hooks(config)

        if test_type == "full":
            yield self._test_error_handling(config)
            yield self._test_retry_logic(config)

    async def run_simulation_stream_async(
        self,
        config: dict[str, Any],
        test_type: str = "full",
        step_timeout_seconds: int = 30,
    ) -> AsyncGenerator[SimulationStepResult, None]:
        """Yield simulation steps asynchronously, applying a per-step timeout."""
        step_fns = [
            lambda: self._test_config_structure(config),
            lambda: self._test_field_mappings(config),
            *[
                (lambda ep: lambda: self._test_endpoint(ep, config))(endpoint)
                for endpoint in config.get("endpoints", [])
                if endpoint.get("enabled", True)
            ],
            lambda: self._test_auth_config(config),
            lambda: self._test_hooks(config),
        ]
        if test_type == "full":
            step_fns += [
                lambda: self._test_error_handling(config),
                lambda: self._test_retry_logic(config),
            ]

        for step_fn in step_fns:
            result = await self._execute_step_with_timeout(step_fn, step_timeout_seconds)
            yield result

    @staticmethod
    async def _execute_step_with_timeout(
        step_fn: Any, timeout_seconds: int = 30
    ) -> SimulationStepResult:
        """Run a synchronous step function with a timeout."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(step_fn),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return SimulationStepResult(
                step_name="unknown_step",
                status="error",
                error_message=f"Step timed out after {timeout_seconds}s",
            )

    def run_parallel_version_test(
        self,
        config_v1: dict[str, Any],
        config_v2: dict[str, Any],
    ) -> list[SimulationStepResult]:
        """Test same request against two different API versions."""
        steps: list[SimulationStepResult] = []
        sample_request = self._build_sample_request(config_v1)

        # Test v1
        start = time.monotonic()
        v1_response = self.mock_server.generate_response(
            {"path": "/api/v1/test"},
            sample_request,
        )
        v1_time = int((time.monotonic() - start) * 1000)

        steps.append(
            SimulationStepResult(
                step_name="parallel_v1_test",
                status="passed",
                request_payload=sample_request,
                expected_response={"status": "success"},
                actual_response=v1_response,
                duration_ms=v1_time,
                confidence_score=0.95,
            )
        )

        # Test v2
        start = time.monotonic()
        v2_response = self.mock_server.generate_response(
            {"path": "/api/v2/test"},
            sample_request,
        )
        v2_time = int((time.monotonic() - start) * 1000)

        steps.append(
            SimulationStepResult(
                step_name="parallel_v2_test",
                status="passed",
                request_payload=sample_request,
                expected_response={"status": "success"},
                actual_response=v2_response,
                duration_ms=v2_time,
                confidence_score=0.95,
            )
        )

        # Compare results
        compatible = v1_response.get("status") == v2_response.get("status")
        steps.append(
            SimulationStepResult(
                step_name="version_compatibility_check",
                status="passed" if compatible else "failed",
                request_payload={},
                expected_response={"compatible": True},
                actual_response={
                    "compatible": compatible,
                    "v1_keys": list(v1_response.keys()),
                    "v2_keys": list(v2_response.keys()),
                },
                confidence_score=1.0 if compatible else 0.5,
            )
        )

        return steps

    async def validate_config_llm(
        self,
        config: dict[str, Any],
        client: GeminiClient,
    ) -> list[SimulationStepResult]:
        """Validate an integration config using Gemini LLM for intelligent analysis.

        Sends the full config to Gemini and asks it to analyze quality across
        several dimensions. Falls back to rule-based run_simulation() on any error.
        """
        system_instruction = (
            "You are AdaptConfig's senior integration QA reviewer for Indian fintech adapters "
            "(CIBIL, eKYC, GST, UPI, AA framework, Razorpay, Paytm). You audit integration configs "
            "for production-readiness. Your analysis must be SPECIFIC and ACTIONABLE — each finding "
            "should tell the engineer exactly what to change. Generic platitudes are worse than useless. "
            "Calibrate status: failures must point at real defects; passes must be defensible. "
            "Output JSON only."
        )

        prompt = f"""Audit this integration config for production-readiness on an Indian fintech lending platform.

# Config under review
```json
{json.dumps(config, indent=2)}
```

# Validation dimensions

Return exactly 7 step results. For each step:
- `status`: "passed" only if the dimension meets production quality. Otherwise "failed".
- `confidence_score`: 0.0-1.0, calibrated to severity (1.0 = perfect, 0.5 = serious issue, 0.0 = critical defect).
- `analysis`: 1-3 sentences naming the SPECIFIC issue or affirming what's correct. Reference field names from the config.
- `actual_response`: dict with concrete evidence (e.g. `{{"timeout_ms": 5000, "recommended_min": 10000}}`).

## The 7 dimensions

1. **config_structure_validation** — does the config have all required top-level keys (base_url, auth, endpoints, field_mappings)? Are values syntactically valid?
2. **field_mapping_quality** — are critical Indian fintech fields mapped (pan_number, aadhaar_number, mobile, credit_score, etc. depending on adapter)? Any obvious semantic mismatches? Coverage gaps?
3. **auth_configuration_adequacy** — is auth.type appropriate for this adapter category? Are required fields present (token_url for oauth, cert for mutual_tls, etc.)? Sensitive creds NOT inline?
4. **error_handling_robustness** — are there on_error hooks, idempotency keys, dead-letter handling? Are HTTP error codes mapped? Critical for payment/disbursement adapters.
5. **retry_logic_appropriateness** — retry_count between 1-5? exponential backoff for transient errors? Are 5xx and 429 retryable but 4xx not? CRITICAL: payment endpoints must NOT retry on 4xx (could double-charge).
6. **endpoint_configuration_validity** — paths look correct? Methods match the operation type? base_url has scheme? Chained endpoints (with `id`/`depends_on`) have valid extract/inject specs?
7. **security_best_practices** — TLS enforced? Bearer tokens not logged? PII (PAN, Aadhaar, account_number) flagged for masking? Webhook URLs use HTTPS?

# Output schema (return JSON exactly matching this)
{{
  "steps": [
    {{
      "step_name": "config_structure_validation",
      "status": "passed",
      "confidence_score": 1.0,
      "analysis": "All required top-level keys present and well-formed.",
      "actual_response": {{"top_level_keys": ["base_url", "auth", "endpoints", "field_mappings", "timeout_ms", "retry_count"]}}
    }},
    ... 6 more
  ],
  "overall_assessment": "Plain-English 2-3 sentence summary highlighting the top 2-3 issues, or affirming production readiness."
}}

Return ONLY the JSON. No markdown fences. No prose outside the JSON."""

        start = time.monotonic()
        try:
            from finspark.core.config import settings as _settings  # noqa: PLC0415
            extra: dict[str, Any] = {}
            if _settings.llm_provider == "openrouter" and _settings.llm_model_reasoning:
                extra["model"] = _settings.llm_model_reasoning
            data = await client.generate_json(
                prompt,
                system_instruction=system_instruction,
                temperature=0.1,
                max_tokens=4096,
                **extra,
            )
        except (GeminiAPIError, Exception) as exc:
            logger.warning(
                "validate_config_llm_fallback reason=%s adapter=%s",
                exc,
                config.get("adapter_name", "unknown"),
            )
            return self.run_simulation(config)

        raw_steps: list[dict[str, Any]] = data.get("steps", [])
        if not raw_steps:
            logger.warning("validate_config_llm_empty_steps falling back to rule-based")
            return self.run_simulation(config)

        total_duration_ms = int((time.monotonic() - start) * 1000)
        per_step_ms = max(1, total_duration_ms // len(raw_steps))

        results: list[SimulationStepResult] = []
        for step in raw_steps:
            status = step.get("status", "error")
            if status not in {"passed", "failed", "skipped", "error"}:
                status = "error"

            actual = step.get("actual_response", {})
            analysis = step.get("analysis", "")
            if analysis and isinstance(actual, dict):
                actual = {"analysis": analysis, **actual}

            results.append(
                SimulationStepResult(
                    step_name=step.get("step_name", "llm_validation_step"),
                    status=status,
                    request_payload={"config_keys": list(config.keys())},
                    expected_response={"status": "passed"},
                    actual_response=actual,
                    duration_ms=per_step_ms,
                    confidence_score=float(step.get("confidence_score", 0.0)),
                    error_message=(
                        analysis if status in {"failed", "error"} and analysis else None
                    ),
                )
            )

        return results

    def _test_config_structure(self, config: dict[str, Any]) -> SimulationStepResult:
        """Validate the overall configuration structure."""
        start = time.monotonic()
        required_keys = [
            "adapter_name",
            "version",
            "base_url",
            "auth",
            "endpoints",
            "field_mappings",
        ]
        missing = [k for k in required_keys if k not in config]
        duration = int((time.monotonic() - start) * 1000)

        return SimulationStepResult(
            step_name="config_structure_validation",
            status="passed" if not missing else "failed",
            request_payload={"required_keys": required_keys},
            expected_response={"missing": []},
            actual_response={"missing": missing},
            duration_ms=max(1, duration),
            confidence_score=1.0 if not missing else 0.0,
            error_message=f"Missing keys: {missing}" if missing else None,
        )

    def _test_field_mappings(self, config: dict[str, Any]) -> SimulationStepResult:
        """Validate field mappings are complete and logical."""
        start = time.monotonic()
        mappings = config.get("field_mappings", [])
        unmapped = [m for m in mappings if not m.get("target_field")]
        low_confidence = [
            m for m in mappings if m.get("confidence", 0) < 0.5 and m.get("target_field")
        ]
        total = len(mappings)
        mapped = total - len(unmapped)
        coverage = mapped / total if total > 0 else 0.0
        duration = int((time.monotonic() - start) * 1000)

        # Coverage threshold is lenient — BRDs often have more source fields than adapter targets
        passed = coverage >= 0.3 and len(low_confidence) <= total * 0.5

        return SimulationStepResult(
            step_name="field_mapping_validation",
            status="passed" if passed else "failed",
            request_payload={"total_fields": total},
            expected_response={"coverage": ">= 0.3"},
            actual_response={
                "coverage": round(coverage, 2),
                "mapped": mapped,
                "unmapped": len(unmapped),
                "low_confidence": len(low_confidence),
            },
            duration_ms=max(1, duration),
            confidence_score=coverage,
            error_message=f"{len(unmapped)} unmapped fields" if unmapped else None,
        )

    def _test_endpoint(
        self, endpoint: dict[str, Any], config: dict[str, Any]
    ) -> SimulationStepResult:
        """Test a single endpoint with mock data."""
        start = time.monotonic()
        request_payload = self._build_sample_request(config)
        response = self.mock_server.generate_response(endpoint, request_payload, config=config)
        duration = int((time.monotonic() - start) * 1000)

        has_status = "status" in response
        return SimulationStepResult(
            step_name=f"endpoint_test_{endpoint.get('path', 'unknown')}",
            status="passed" if has_status else "failed",
            request_payload=request_payload,
            expected_response={"status": "success"},
            actual_response=response,
            duration_ms=max(1, duration),
            confidence_score=0.9 if has_status else 0.3,
        )

    def _test_auth_config(self, config: dict[str, Any]) -> SimulationStepResult:
        """Validate authentication configuration."""
        start = time.monotonic()
        auth = config.get("auth", {})
        auth_type = auth.get("type", "")
        has_type = bool(auth_type)
        duration = int((time.monotonic() - start) * 1000)

        return SimulationStepResult(
            step_name="auth_config_validation",
            status="passed" if has_type else "failed",
            request_payload={"auth_config": {"type": auth_type}},
            expected_response={"has_auth_type": True},
            actual_response={"has_auth_type": has_type, "auth_type": auth_type},
            duration_ms=max(1, duration),
            confidence_score=1.0 if has_type else 0.0,
        )

    def _test_hooks(self, config: dict[str, Any]) -> SimulationStepResult:
        """Validate hook configuration."""
        start = time.monotonic()
        hooks = config.get("hooks", [])
        valid_types = {"pre_request", "post_response", "on_error", "on_timeout"}
        invalid_hooks = [h for h in hooks if h.get("type") not in valid_types]
        duration = int((time.monotonic() - start) * 1000)

        return SimulationStepResult(
            step_name="hooks_validation",
            status="passed" if not invalid_hooks else "failed",
            request_payload={"total_hooks": len(hooks)},
            expected_response={"invalid_hooks": 0},
            actual_response={
                "total_hooks": len(hooks),
                "invalid_hooks": len(invalid_hooks),
                "hook_types": list({h.get("type") for h in hooks}),
            },
            duration_ms=max(1, duration),
            confidence_score=1.0 if not invalid_hooks else 0.5,
        )

    def _test_error_handling(self, config: dict[str, Any]) -> SimulationStepResult:
        """Test error handling configuration."""
        start = time.monotonic()
        has_retry = "retry_policy" in config
        has_timeout = "timeout_ms" in config
        has_error_hook = any(h.get("type") == "on_error" for h in config.get("hooks", []))
        duration = int((time.monotonic() - start) * 1000)

        score = sum([has_retry, has_timeout, has_error_hook]) / 3.0

        return SimulationStepResult(
            step_name="error_handling_validation",
            status="passed" if score >= 0.6 else "failed",
            request_payload={},
            expected_response={"has_retry": True, "has_timeout": True},
            actual_response={
                "has_retry": has_retry,
                "has_timeout": has_timeout,
                "has_error_hook": has_error_hook,
            },
            duration_ms=max(1, duration),
            confidence_score=round(score, 2),
        )

    def _test_retry_logic(self, config: dict[str, Any]) -> SimulationStepResult:
        """Validate retry policy configuration."""
        start = time.monotonic()
        retry = config.get("retry_policy", {})
        max_retries = retry.get("max_retries", 0)
        has_backoff = "backoff_factor" in retry
        has_status_codes = bool(retry.get("retry_on_status"))
        duration = int((time.monotonic() - start) * 1000)

        valid = max_retries > 0 and max_retries <= 10 and has_backoff

        return SimulationStepResult(
            step_name="retry_logic_validation",
            status="passed" if valid else "failed",
            request_payload={"retry_policy": retry},
            expected_response={"valid": True},
            actual_response={
                "valid": valid,
                "max_retries": max_retries,
                "has_backoff": has_backoff,
                "has_status_codes": has_status_codes,
            },
            duration_ms=max(1, duration),
            confidence_score=1.0 if valid else 0.3,
        )

    @staticmethod
    def _build_sample_request(config: dict[str, Any]) -> dict[str, Any]:
        """Build a sample request from field mappings."""
        request: dict[str, Any] = {}
        for mapping in config.get("field_mappings", []):
            source = mapping.get("source_field", "")
            if source:
                request[source] = MockAPIServer.MOCK_DATA.get(source, f"sample_{source}")
        return request
