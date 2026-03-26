"""Integration tests for the search API endpoint."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import Adapter, AdapterVersion


@pytest_asyncio.fixture
async def seeded_client(db_session: AsyncSession, client: AsyncClient) -> AsyncClient:
    """Seed adapters and return the test client."""
    adapter = Adapter(
        name="CIBIL Credit Bureau",
        category="bureau",
        description="Credit score integration",
    )
    db_session.add(adapter)
    await db_session.flush()

    version = AdapterVersion(
        adapter_id=adapter.id,
        version="v1",
        auth_type="oauth2",
        version_order=1,
    )
    db_session.add(version)
    await db_session.commit()

    return client


class TestSearchAPI:
    """Integration tests for GET /api/v1/search."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/v1/search/", params={"q": "credit bureau"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert len(data["adapters"]) >= 1

    @pytest.mark.asyncio
    async def test_search_oauth2_filter(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/v1/search/", params={"q": "oauth2"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["adapters"]) >= 1

    @pytest.mark.asyncio
    async def test_search_empty_results(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/v1/search/", params={"q": "xyznothing"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_search_missing_query(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/v1/search/")
        assert resp.status_code == 422  # validation error
