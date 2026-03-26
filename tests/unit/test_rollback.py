"""Tests for configuration rollback functionality."""

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.configuration import Configuration, ConfigurationHistory
from finspark.services.config_engine.rollback import RollbackManager


def _make_config(tenant_id: str = "test-tenant", version: int = 1) -> Configuration:
    return Configuration(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name="Test Config",
        adapter_version_id=str(uuid.uuid4()),
        status="configured",
        version=version,
        field_mappings=json.dumps([{"source_field": "pan", "target_field": "pan_number"}]),
        transformation_rules=json.dumps([]),
        hooks=json.dumps([]),
        full_config=json.dumps(
            {
                "base_url": "https://api.test.com/v1",
                "auth": {"type": "api_key"},
                "endpoints": [{"path": "/test", "method": "POST"}],
                "field_mappings": [{"source_field": "pan", "target_field": "pan_number"}],
            }
        ),
    )


def _make_history(
    config_id: str,
    tenant_id: str,
    version: int,
    change_type: str = "created",
    new_value: dict | None = None,
    previous_value: dict | None = None,
) -> ConfigurationHistory:
    return ConfigurationHistory(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        configuration_id=config_id,
        version=version,
        change_type=change_type,
        new_value=json.dumps(new_value) if new_value else None,
        previous_value=json.dumps(previous_value) if previous_value else None,
        changed_by="tester",
    )


TENANT = "test-tenant"

V1_STATE = {
    "field_mappings": [{"source_field": "pan", "target_field": "pan_number"}],
    "transformation_rules": [],
    "hooks": [],
    "auth_config": None,
    "full_config": {
        "base_url": "https://api.test.com/v1",
        "auth": {"type": "api_key"},
        "endpoints": [{"path": "/test", "method": "POST"}],
        "field_mappings": [{"source_field": "pan", "target_field": "pan_number"}],
    },
    "status": "configured",
    "version": 1,
}

V2_STATE = {
    "field_mappings": [{"source_field": "pan", "target_field": "pan_id"}],
    "transformation_rules": [{"name": "upper_pan"}],
    "hooks": [],
    "auth_config": None,
    "full_config": {
        "base_url": "https://api.test.com/v2",
        "auth": {"type": "oauth2"},
        "endpoints": [{"path": "/test", "method": "POST"}],
        "field_mappings": [{"source_field": "pan", "target_field": "pan_id"}],
    },
    "status": "configured",
    "version": 2,
}


@pytest.mark.asyncio
class TestRollbackManagerSnapshot:
    async def test_snapshot_creates_history_entry(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        mgr = RollbackManager(db_session)
        entry = await mgr.snapshot(config.id, TENANT, changed_by="tester")

        assert entry.configuration_id == config.id
        assert entry.version == 1
        assert entry.change_type == "updated"
        assert entry.changed_by == "tester"

        saved = json.loads(entry.new_value)  # type: ignore[arg-type]
        assert saved["status"] == "configured"
        assert saved["version"] == 1

    async def test_snapshot_increments_version(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        mgr = RollbackManager(db_session)
        first = await mgr.snapshot(config.id, TENANT)
        second = await mgr.snapshot(config.id, TENANT)

        assert first.version == 1
        assert second.version == 2

    async def test_snapshot_records_previous_value(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        mgr = RollbackManager(db_session)
        first = await mgr.snapshot(config.id, TENANT)
        second = await mgr.snapshot(config.id, TENANT)

        assert first.previous_value is None
        assert second.previous_value is not None


@pytest.mark.asyncio
class TestRollbackManagerRollback:
    async def test_rollback_restores_version(self, db_session: AsyncSession) -> None:
        config = _make_config(version=2)
        config.field_mappings = json.dumps(V2_STATE["field_mappings"])
        config.full_config = json.dumps(V2_STATE["full_config"])
        db_session.add(config)
        await db_session.flush()

        # Seed history v1 and v2
        h1 = _make_history(config.id, TENANT, 1, "created", V1_STATE)
        h2 = _make_history(config.id, TENANT, 2, "updated", V2_STATE, V1_STATE)
        db_session.add_all([h1, h2])
        await db_session.flush()

        mgr = RollbackManager(db_session)
        restored = await mgr.rollback(config.id, 1, TENANT, changed_by="tester")

        assert restored.status == "rollback"
        assert restored.version == 3  # was 2, incremented
        restored_full = json.loads(restored.full_config)  # type: ignore[arg-type]
        assert restored_full["base_url"] == "https://api.test.com/v1"

    async def test_rollback_invalid_version_raises(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        h1 = _make_history(config.id, TENANT, 1, "created", V1_STATE)
        db_session.add(h1)
        await db_session.flush()

        mgr = RollbackManager(db_session)
        with pytest.raises(ValueError, match="Version 99 not found"):
            await mgr.rollback(config.id, 99, TENANT)

    async def test_rollback_nonexistent_config_raises(self, db_session: AsyncSession) -> None:
        mgr = RollbackManager(db_session)
        with pytest.raises(ValueError, match="not found"):
            await mgr.rollback("nonexistent", 1, TENANT)

    async def test_rollback_creates_history_entries(self, db_session: AsyncSession) -> None:
        config = _make_config(version=2)
        db_session.add(config)
        await db_session.flush()

        h1 = _make_history(config.id, TENANT, 1, "created", V1_STATE)
        h2 = _make_history(config.id, TENANT, 2, "updated", V2_STATE)
        db_session.add_all([h1, h2])
        await db_session.flush()

        mgr = RollbackManager(db_session)
        await mgr.rollback(config.id, 1, TENANT, changed_by="tester")

        # Should have: v1(created), v2(updated), v3(pre_rollback snapshot), v4(rollback)
        stmt = (
            select(ConfigurationHistory)
            .where(ConfigurationHistory.configuration_id == config.id)
            .order_by(ConfigurationHistory.version.asc())
        )
        result = await db_session.execute(stmt)
        entries = result.scalars().all()
        assert len(entries) == 4
        assert entries[2].change_type == "pre_rollback"
        assert entries[3].change_type == "rollback"


@pytest.mark.asyncio
class TestRollbackManagerListVersions:
    async def test_list_versions_returns_ordered(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        h1 = _make_history(config.id, TENANT, 1, "created", V1_STATE)
        h2 = _make_history(config.id, TENANT, 2, "updated", V2_STATE)
        db_session.add_all([h1, h2])
        await db_session.flush()

        mgr = RollbackManager(db_session)
        versions = await mgr.list_versions(config.id, TENANT)

        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[1].version == 2

    async def test_list_versions_empty_for_no_history(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        mgr = RollbackManager(db_session)
        versions = await mgr.list_versions(config.id, TENANT)
        assert versions == []


@pytest.mark.asyncio
class TestRollbackManagerCompareVersions:
    async def test_compare_versions_shows_diff(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        h1 = _make_history(config.id, TENANT, 1, "created", V1_STATE)
        h2 = _make_history(config.id, TENANT, 2, "updated", V2_STATE)
        db_session.add_all([h1, h2])
        await db_session.flush()

        mgr = RollbackManager(db_session)
        comparison = await mgr.compare_versions(config.id, 1, 2, TENANT)

        assert comparison.configuration_id == config.id
        assert comparison.version_a == 1
        assert comparison.version_b == 2
        assert comparison.total_changes > 0

    async def test_compare_versions_invalid_version_raises(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        h1 = _make_history(config.id, TENANT, 1, "created", V1_STATE)
        db_session.add(h1)
        await db_session.flush()

        mgr = RollbackManager(db_session)
        with pytest.raises(ValueError, match="Version 5 not found"):
            await mgr.compare_versions(config.id, 1, 5, TENANT)

    async def test_compare_same_version_no_diffs(self, db_session: AsyncSession) -> None:
        config = _make_config()
        db_session.add(config)
        await db_session.flush()

        h1 = _make_history(config.id, TENANT, 1, "created", V1_STATE)
        db_session.add(h1)
        await db_session.flush()

        mgr = RollbackManager(db_session)
        comparison = await mgr.compare_versions(config.id, 1, 1, TENANT)
        assert comparison.total_changes == 0


@pytest.mark.asyncio
class TestRollbackAPIEndpoints:
    """Integration tests for rollback API routes."""

    async def _seed_config(self, db_session: AsyncSession) -> tuple[str, str]:
        """Helper: create a config with two history entries, return (config_id, adapter_version_id)."""
        adapter_version_id = str(uuid.uuid4())
        config = Configuration(
            id=str(uuid.uuid4()),
            tenant_id="test-tenant",
            name="API Test Config",
            adapter_version_id=adapter_version_id,
            status="configured",
            version=2,
            field_mappings=json.dumps(V2_STATE["field_mappings"]),
            transformation_rules=json.dumps(V2_STATE["transformation_rules"]),
            hooks=json.dumps([]),
            full_config=json.dumps(V2_STATE["full_config"]),
        )
        db_session.add(config)
        await db_session.flush()

        h1 = _make_history(config.id, "test-tenant", 1, "created", V1_STATE)
        h2 = _make_history(config.id, "test-tenant", 2, "updated", V2_STATE, V1_STATE)
        db_session.add_all([h1, h2])
        await db_session.flush()

        return config.id, adapter_version_id

    async def test_get_history(self, client, db_session: AsyncSession) -> None:
        config_id, _ = await self._seed_config(db_session)

        resp = await client.get(f"/api/v1/configurations/{config_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]) == 2
        assert data["data"][0]["version"] == 1

    async def test_post_rollback(self, client, db_session: AsyncSession) -> None:
        config_id, _ = await self._seed_config(db_session)

        resp = await client.post(
            f"/api/v1/configurations/{config_id}/rollback",
            json={"target_version": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["restored_version"] == 3
        assert data["data"]["status"] == "rollback"

    async def test_rollback_invalid_version_returns_400(
        self, client, db_session: AsyncSession
    ) -> None:
        config_id, _ = await self._seed_config(db_session)

        resp = await client.post(
            f"/api/v1/configurations/{config_id}/rollback",
            json={"target_version": 999},
        )
        assert resp.status_code == 400

    async def test_rollback_nonexistent_config_returns_404(self, client) -> None:
        resp = await client.post(
            "/api/v1/configurations/nonexistent-id/rollback",
            json={"target_version": 1},
        )
        assert resp.status_code == 404

    async def test_compare_versions_endpoint(self, client, db_session: AsyncSession) -> None:
        config_id, _ = await self._seed_config(db_session)

        resp = await client.get(
            f"/api/v1/configurations/{config_id}/history/compare",
            params={"v1": 1, "v2": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total_changes"] > 0
        assert data["data"]["version_a"] == 1
        assert data["data"]["version_b"] == 2
