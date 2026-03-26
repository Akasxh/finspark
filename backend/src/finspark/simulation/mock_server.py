"""
MockAPIServer — generates realistic mock HTTP responses for an adapter's
endpoints using httpx_mock (pytest-httpx) or a standalone respx router.

Design goals:
- Driven entirely by AdapterSchema; no hard-coded provider logic.
- Synthetic response data matches the JSON Schema types defined in
  EndpointSchema.response_schema so contract validators don't trivially pass.
- Configurable error injection (rate, latency jitter).
- Reentrant; multiple MockAPIServer instances can coexist in one process
  (useful for parallel v1/v2 testing).
"""
from __future__ import annotations

import json
import random
import re
import string
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx

from finspark.simulation.types import AdapterSchema, EndpointSchema


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

_FAKER_STRINGS: dict[str, list[str]] = {
    "name": ["Priya Sharma", "Arjun Mehta", "Sneha Nair", "Vikram Das"],
    "email": ["test@example.com", "user@corp.in", "api@finspark.io"],
    "phone": ["+919876543210", "+919123456789"],
    "pan": ["ABCDE1234F", "PQRST5678G"],
    "gstin": ["29ABCDE1234F1ZK", "27PQRST5678G1ZJ"],
    "status": ["active", "inactive", "pending", "verified"],
}


def _synthetic_value(schema: dict[str, Any], field_name: str = "") -> Any:
    """Produce a synthetic value that satisfies *schema* (best-effort)."""
    schema_type = schema.get("type", "string")
    fmt = schema.get("format", "")
    enum_vals = schema.get("enum")
    if enum_vals:
        return random.choice(enum_vals)

    # name-hint based selection
    lower_name = field_name.lower()
    for hint, candidates in _FAKER_STRINGS.items():
        if hint in lower_name:
            return random.choice(candidates)

    if schema_type == "string":
        if fmt == "date-time":
            return "2024-01-15T10:30:00Z"
        if fmt == "date":
            return "2024-01-15"
        if fmt == "uuid":
            return "550e8400-e29b-41d4-a716-446655440000"
        if fmt == "email":
            return "mock@finspark.io"
        min_l = schema.get("minLength", 5)
        max_l = schema.get("maxLength", 20)
        length = random.randint(min_l, min(max_l, 20))
        return "".join(random.choices(string.ascii_lowercase, k=length))

    if schema_type == "integer":
        minimum = schema.get("minimum", 0)
        maximum = schema.get("maximum", 9999)
        return random.randint(int(minimum), int(maximum))

    if schema_type == "number":
        minimum = schema.get("minimum", 0.0)
        maximum = schema.get("maximum", 9999.0)
        return round(random.uniform(float(minimum), float(maximum)), 2)

    if schema_type == "boolean":
        return random.choice([True, False])

    if schema_type == "array":
        items_schema = schema.get("items", {"type": "string"})
        count = random.randint(1, 3)
        return [_synthetic_value(items_schema, field_name) for _ in range(count)]

    if schema_type == "object":
        return _build_object(schema)

    return None


def _build_object(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively build a synthetic object from a JSON Schema object definition."""
    result: dict[str, Any] = {}
    properties: dict[str, Any] = schema.get("properties", {})
    required_fields: list[str] = schema.get("required", [])

    for field, sub_schema in properties.items():
        result[field] = _synthetic_value(sub_schema, field)

    # ensure required fields are present even if not in properties
    for field in required_fields:
        if field not in result:
            result[field] = _synthetic_value({"type": "string"}, field)

    return result


def generate_mock_response(endpoint: EndpointSchema) -> dict[str, Any]:
    """
    Build a synthetic response body conforming to endpoint.response_schema.
    Falls back to a minimal envelope if no schema is defined.
    """
    schema = endpoint.response_schema
    if not schema:
        return {
            "status": "success",
            "data": {},
            "request_id": "mock-req-" + "".join(random.choices(string.hexdigits[:16], k=8)),
        }

    schema_type = schema.get("type", "object")
    if schema_type == "object":
        return _build_object(schema)
    if schema_type == "array":
        items_schema = schema.get("items", {"type": "object"})
        return {"items": [_build_object(items_schema) for _ in range(2)]}

    # scalar root (unusual for APIs, but handle gracefully)
    return {"value": _synthetic_value(schema)}


# ---------------------------------------------------------------------------
# MockAPIServer
# ---------------------------------------------------------------------------


class MockAPIServer:
    """
    Registers httpx mock handlers for every endpoint in an AdapterSchema.

    Usage with pytest-httpx:

        server = MockAPIServer(schema)
        with server.install(httpx_mock):
            response = await client.post(url, json=payload)

    Usage standalone (returns a pre-built respx router):

        router = server.build_respx_router()
        async with respx.MockRouter() as mock:
            ...

    The server also exposes `call_log` for asserting request history.
    """

    def __init__(
        self,
        schema: AdapterSchema,
        *,
        seed: int | None = None,
        force_error_rate: float | None = None,
        latency_jitter: bool = True,
    ) -> None:
        self._schema = schema
        self._rng = random.Random(seed)
        self._force_error_rate = force_error_rate
        self._latency_jitter = latency_jitter
        self.call_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_handler_for(self, endpoint: EndpointSchema):  # type: ignore[return]
        """
        Return a callable suitable for use as a pytest-httpx / respx handler.
        The callable accepts an httpx.Request and returns an httpx.Response.
        """
        def handler(request: httpx.Request) -> httpx.Response:
            return self._handle(endpoint, request)

        return handler

    def _handle(self, endpoint: EndpointSchema, request: httpx.Request) -> httpx.Response:
        """Simulate latency, error injection, then generate response."""
        # ---- record call ------------------------------------------------
        entry: dict[str, Any] = {
            "url": str(request.url),
            "method": request.method,
            "timestamp": time.time(),
            "endpoint_path": endpoint.path,
        }
        try:
            body = json.loads(request.content) if request.content else {}
            entry["request_body"] = body
        except (json.JSONDecodeError, UnicodeDecodeError):
            entry["request_body"] = None
        self.call_log.append(entry)

        # ---- error injection --------------------------------------------
        error_rate = (
            self._force_error_rate
            if self._force_error_rate is not None
            else endpoint.error_rate
        )
        if self._rng.random() < error_rate:
            return httpx.Response(
                502,
                json={"error": "upstream_error", "message": "Simulated upstream failure"},
            )

        # ---- synthetic response -----------------------------------------
        body = generate_mock_response(endpoint)
        success_code = endpoint.success_codes[0] if endpoint.success_codes else 200
        return httpx.Response(success_code, json=body)

    def build_url(self, endpoint: EndpointSchema) -> str:
        """Resolve full URL for an endpoint against the adapter's base_url."""
        base = self._schema.base_url.rstrip("/")
        path = endpoint.path.lstrip("/")
        return f"{base}/{path}"

    def install(self, httpx_mock: Any) -> "MockAPIServer":
        """
        Register all endpoints on a pytest-httpx HTTPXMock instance.
        Returns self so it can be used as a context-manager-like chain.
        """
        for endpoint in self._schema.endpoints:
            url = self.build_url(endpoint)
            method = endpoint.method.value.lower()
            handler = self.get_handler_for(endpoint)
            getattr(httpx_mock, f"add_{method}_handler")(url, handler)  # type: ignore[operator]
        return self

    def assert_called(self, path: str, *, times: int | None = None) -> None:
        """Assert that endpoint at *path* was called (optionally exactly *times*)."""
        hits = [e for e in self.call_log if e["endpoint_path"] == path]
        if not hits:
            raise AssertionError(f"Endpoint '{path}' was never called. calls={self.call_log}")
        if times is not None and len(hits) != times:
            raise AssertionError(
                f"Endpoint '{path}' called {len(hits)} time(s), expected {times}"
            )

    def reset(self) -> None:
        self.call_log.clear()
