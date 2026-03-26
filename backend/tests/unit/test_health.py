"""Smoke test: health endpoint returns 200."""

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
