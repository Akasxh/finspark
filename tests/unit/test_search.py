"""Tests for integration search service."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import Adapter, AdapterVersion
from finspark.models.configuration import Configuration
from finspark.models.simulation import Simulation
from finspark.services.search import IntegrationSearch


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession) -> AsyncSession:
    """Seed DB with test data for search."""
    # Adapters
    cibil = Adapter(
        name="CIBIL Credit Bureau", category="bureau", description="Credit score integration"
    )
    ekyc = Adapter(
        name="Aadhaar eKYC Provider", category="kyc", description="Aadhaar-based electronic KYC"
    )
    payment = Adapter(name="Payment Gateway", category="payment", description="Payment processing")
    db_session.add_all([cibil, ekyc, payment])
    await db_session.flush()

    # Versions
    v1 = AdapterVersion(adapter_id=cibil.id, version="v1", auth_type="api_key", version_order=1)
    v2 = AdapterVersion(adapter_id=cibil.id, version="v2", auth_type="oauth2", version_order=2)
    v_kyc = AdapterVersion(adapter_id=ekyc.id, version="v1", auth_type="api_key", version_order=1)
    v_pay = AdapterVersion(
        adapter_id=payment.id, version="v1", auth_type="api_key", version_order=1
    )
    db_session.add_all([v1, v2, v_kyc, v_pay])
    await db_session.flush()

    # Configurations
    cfg1 = Configuration(
        name="CIBIL Config",
        tenant_id="t1",
        adapter_version_id=v1.id,
        status="active",
    )
    cfg2 = Configuration(
        name="KYC Config",
        tenant_id="t1",
        adapter_version_id=v_kyc.id,
        status="draft",
    )
    cfg3 = Configuration(
        name="Payment Config",
        tenant_id="t2",
        adapter_version_id=v_pay.id,
        status="active",
    )
    db_session.add_all([cfg1, cfg2, cfg3])
    await db_session.flush()

    # Simulations
    sim1 = Simulation(
        configuration_id=cfg1.id,
        tenant_id="t1",
        status="failed",
        test_type="full",
        total_tests=5,
        passed_tests=3,
        failed_tests=2,
    )
    sim2 = Simulation(
        configuration_id=cfg1.id,
        tenant_id="t1",
        status="passed",
        test_type="smoke",
        total_tests=3,
        passed_tests=3,
        failed_tests=0,
    )
    db_session.add_all([sim1, sim2])
    await db_session.flush()

    return db_session


class TestIntegrationSearch:
    """Unit tests for IntegrationSearch."""

    @pytest.mark.asyncio
    async def test_search_by_category_kyc(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("all KYC integrations", tenant_id="t1")
        assert len(results.adapters) >= 1
        assert results.adapters[0].name == "Aadhaar eKYC Provider"

    @pytest.mark.asyncio
    async def test_search_by_category_bureau(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("credit bureau", tenant_id="t1")
        names = [r.name for r in results.adapters]
        assert "CIBIL Credit Bureau" in names

    @pytest.mark.asyncio
    async def test_search_active_configs(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("active credit bureau configs", tenant_id="t1")
        # Should find the active CIBIL config
        assert len(results.configurations) >= 1
        assert results.configurations[0].details["status"] == "active"

    @pytest.mark.asyncio
    async def test_search_failed_simulations(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("failed simulations", tenant_id="t1")
        assert len(results.simulations) >= 1
        assert results.simulations[0].details["status"] == "failed"

    @pytest.mark.asyncio
    async def test_search_oauth2_adapters(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("adapters with OAuth2", tenant_id="t1")
        assert len(results.adapters) >= 1
        # CIBIL has oauth2 version
        cibil_result = next((r for r in results.adapters if "CIBIL" in r.name), None)
        assert cibil_result is not None
        assert "oauth2" in cibil_result.details["auth_types"]

    @pytest.mark.asyncio
    async def test_search_tenant_isolation(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        # t2 has a payment config, t1 doesn't
        results = await svc.search("active payment", tenant_id="t1")
        config_ids = [r.id for r in results.configurations]
        # t1 should not see t2's config
        results_t2 = await svc.search("active payment", tenant_id="t2")
        assert len(results_t2.configurations) >= 1
        # No overlap
        for c in results_t2.configurations:
            assert c.id not in config_ids

    @pytest.mark.asyncio
    async def test_search_empty_query_no_crash(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("xyznonexistent", tenant_id="t1")
        assert results.total == 0

    @pytest.mark.asyncio
    async def test_results_sorted_by_score(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("credit bureau", tenant_id="t1")
        if len(results.adapters) >= 2:
            assert results.adapters[0].score >= results.adapters[1].score

    @pytest.mark.asyncio
    async def test_search_total_count(self, seeded_db: AsyncSession) -> None:
        svc = IntegrationSearch(seeded_db)
        results = await svc.search("KYC", tenant_id="t1")
        assert results.total == (
            len(results.adapters) + len(results.configurations) + len(results.simulations)
        )
