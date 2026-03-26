"""
Sandbox environment isolation per tenant.

Each sandbox:
- Gets its own copy of the IntegrationConfig (no shared mutable state).
- Owns an isolated MockAPIServer instance seeded for determinism.
- Exposes an async httpx.AsyncClient pre-configured for that adapter.
- Is destroyed after use; nothing leaks between tenants.

No network is used; all HTTP calls are intercepted by respx or httpx_mock.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx

from finspark.simulation.mock_server import MockAPIServer
from finspark.simulation.types import AdapterSchema, IntegrationConfig


class Sandbox:
    """
    Isolated simulation environment for one tenant / one adapter run.

    Attributes
    ----------
    sandbox_id : str
    tenant_id  : str
    config     : IntegrationConfig  (deep copy — safe to mutate)
    server     : MockAPIServer
    client     : httpx.AsyncClient  (available inside `activate()` context)
    """

    def __init__(
        self,
        tenant_id: str,
        config: IntegrationConfig,
        schema: AdapterSchema,
        *,
        seed: int | None = None,
        force_error_rate: float | None = None,
    ) -> None:
        self.sandbox_id: str = uuid.uuid4().hex
        self.tenant_id = tenant_id
        # deep-copy so mutations never affect the caller's config
        self.config = config.model_copy(deep=True)
        self.schema = schema
        self.server = MockAPIServer(
            schema,
            seed=seed,
            force_error_rate=force_error_rate,
        )
        self._client: httpx.AsyncClient | None = None
        self._transport: httpx.MockTransport | None = None

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def activate(self) -> AsyncGenerator["Sandbox", None]:
        """
        Enter the sandbox.  Inside this context `self.client` is ready.
        On exit the client is closed and call_log is preserved for inspection.
        """
        transport = _SandboxTransport(self.server)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=self.schema.base_url,
            timeout=httpx.Timeout(30.0),
        ) as client:
            self._client = client
            try:
                yield self
            finally:
                self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Sandbox not activated. Use `async with sandbox.activate()`.")
        return self._client

    def call_log(self) -> list[dict[str, Any]]:
        return list(self.server.call_log)


# ---------------------------------------------------------------------------
# httpx transport that routes to MockAPIServer
# ---------------------------------------------------------------------------


class _SandboxTransport(httpx.AsyncBaseTransport):
    """
    Intercepts every outgoing httpx request and delegates to MockAPIServer.
    Matches on URL path — finds the best matching EndpointSchema.
    """

    def __init__(self, server: MockAPIServer) -> None:
        self._server = server

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        endpoint = self._match_endpoint(str(request.url.path))
        if endpoint is None:
            return httpx.Response(
                404,
                json={
                    "error": "not_found",
                    "message": f"No mock endpoint registered for {request.url.path}",
                },
            )
        return self._server._handle(endpoint, request)

    def _match_endpoint(self, path: str):  # type: ignore[return]
        schema = self._server._schema
        for ep in schema.endpoints:
            # exact match
            if ep.path == path:
                return ep
            # template match: /v1/credit/{pan} → /v1/credit/ABCDE1234F
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", ep.path)
            if re.fullmatch(pattern, path):
                return ep
        # fall back to first endpoint if base path matches prefix
        for ep in schema.endpoints:
            if path.startswith(ep.path.split("{")[0].rstrip("/")):
                return ep
        return None


import re  # noqa: E402 — needed by _SandboxTransport, placed after class def


# ---------------------------------------------------------------------------
# SandboxRegistry — factory / per-tenant registry
# ---------------------------------------------------------------------------


class SandboxRegistry:
    """
    Lightweight per-process registry of active sandboxes.
    Used by IntegrationSimulator to enforce per-tenant isolation.
    """

    def __init__(self) -> None:
        self._active: dict[str, Sandbox] = {}  # sandbox_id → Sandbox

    def create(
        self,
        tenant_id: str,
        config: IntegrationConfig,
        schema: AdapterSchema,
        **kwargs: Any,
    ) -> Sandbox:
        sb = Sandbox(tenant_id, config, schema, **kwargs)
        self._active[sb.sandbox_id] = sb
        return sb

    def release(self, sandbox_id: str) -> None:
        self._active.pop(sandbox_id, None)

    def active_for_tenant(self, tenant_id: str) -> list[Sandbox]:
        return [s for s in self._active.values() if s.tenant_id == tenant_id]

    def __len__(self) -> int:
        return len(self._active)
