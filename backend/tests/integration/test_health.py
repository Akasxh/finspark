"""Integration test: health endpoint — validates the full request stack."""
import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
