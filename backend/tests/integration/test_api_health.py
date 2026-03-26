"""
Health check and meta-endpoint integration tests.

These are the first tests that should pass once the app boots.
They validate infrastructure assumptions before any domain logic runs.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_health_returns_200(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_health_body_shape(client: AsyncClient) -> None:
    resp = await client.get("/health")
    if resp.status_code != 200:
        pytest.skip("Health endpoint not yet implemented")
    body = resp.json()
    assert "status" in body
    assert body["status"] in ("ok", "healthy", "up")


async def test_openapi_json_accessible(client: AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    body = resp.json()
    assert "openapi" in body
    assert "paths" in body


async def test_docs_accessible(client: AsyncClient) -> None:
    """FastAPI's /docs should be available in non-production environments."""
    resp = await client.get("/docs")
    assert resp.status_code == 200


async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/this-route-does-not-exist-xyz")
    assert resp.status_code == 404


async def test_method_not_allowed(client: AsyncClient, tenant_headers: dict[str, str]) -> None:
    """DELETE on a list endpoint should return 405, not 500."""
    resp = await client.delete("/api/v1/adapters", headers=tenant_headers)
    assert resp.status_code in (405, 404)
