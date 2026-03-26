"""Unit tests for adapter version deprecation tracking."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import Adapter, AdapterVersion
from finspark.services.registry.deprecation import DEFAULT_SUNSET_DAYS, DeprecationTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_adapter_with_versions(
    db: AsyncSession,
    *,
    v1_status: str = "deprecated",
    v2_status: str = "active",
) -> tuple[Adapter, AdapterVersion, AdapterVersion]:
    adapter = Adapter(name="Test Adapter", category="bureau", description="test")
    db.add(adapter)
    await db.flush()

    v1 = AdapterVersion(
        adapter_id=adapter.id,
        version="v1",
        version_order=1,
        status=v1_status,
        base_url="https://api.test.com/v1",
        auth_type="api_key",
        endpoints=json.dumps([{"path": "/score", "method": "POST", "description": "Get score"}]),
        request_schema=json.dumps({"type": "object", "required": ["id"]}),
    )
    v2 = AdapterVersion(
        adapter_id=adapter.id,
        version="v2",
        version_order=2,
        status=v2_status,
        base_url="https://api.test.com/v2",
        auth_type="oauth2",
        endpoints=json.dumps(
            [{"path": "/scores", "method": "POST", "description": "Get score v2"}]
        ),
        request_schema=json.dumps({"type": "object", "required": ["id", "consent"]}),
        changelog="Switched to OAuth2, new endpoint paths",
    )
    db.add_all([v1, v2])
    await db.flush()
    return adapter, v1, v2


# ---------------------------------------------------------------------------
# Tests: DeprecationTracker
# ---------------------------------------------------------------------------


class TestGetDeprecatedVersions:
    @pytest.mark.asyncio
    async def test_returns_deprecated_versions(self, db_session: AsyncSession) -> None:
        adapter, v1, _ = await _seed_adapter_with_versions(db_session)
        tracker = DeprecationTracker(db_session)

        deprecated = await tracker.get_deprecated_versions(adapter.id)

        assert len(deprecated) == 1
        assert deprecated[0]["version"] == "v1"
        assert deprecated[0]["sunset_date"] is not None
        assert deprecated[0]["days_until_sunset"] is not None

    @pytest.mark.asyncio
    async def test_returns_empty_when_none_deprecated(self, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(
            db_session, v1_status="active", v2_status="active"
        )
        tracker = DeprecationTracker(db_session)

        deprecated = await tracker.get_deprecated_versions(adapter.id)
        assert deprecated == []


class TestCheckVersionHealth:
    @pytest.mark.asyncio
    async def test_deprecated_version_health(self, db_session: AsyncSession) -> None:
        adapter, v1, v2 = await _seed_adapter_with_versions(db_session)
        tracker = DeprecationTracker(db_session)

        health = await tracker.check_version_health(adapter.id, "v1")

        assert health["status"] == "deprecated"
        assert health["replacement_version"] == "v2"
        assert health["days_until_sunset"] is not None
        assert health["sunset_date"] is not None

    @pytest.mark.asyncio
    async def test_active_version_health(self, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(db_session)
        tracker = DeprecationTracker(db_session)

        health = await tracker.check_version_health(adapter.id, "v2")

        assert health["status"] == "active"
        assert health["days_until_sunset"] is None
        assert health["replacement_version"] is None

    @pytest.mark.asyncio
    async def test_not_found_version(self, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(db_session)
        tracker = DeprecationTracker(db_session)

        health = await tracker.check_version_health(adapter.id, "v99")

        assert health["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_deprecated_without_replacement(self, db_session: AsyncSession) -> None:
        """Deprecated version with no higher active version."""
        adapter, _, _ = await _seed_adapter_with_versions(
            db_session, v1_status="deprecated", v2_status="deprecated"
        )
        tracker = DeprecationTracker(db_session)

        health = await tracker.check_version_health(adapter.id, "v1")

        assert health["status"] == "deprecated"
        assert health["replacement_version"] is None


class TestGetMigrationGuide:
    @pytest.mark.asyncio
    async def test_migration_guide_has_steps(self, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(db_session)
        tracker = DeprecationTracker(db_session)

        guide = await tracker.get_migration_guide(adapter.id, "v1", "v2")

        assert guide["from_version"] == "v1"
        assert guide["to_version"] == "v2"
        assert len(guide["steps"]) > 0

        actions = [s["action"] for s in guide["steps"]]
        assert "update_auth" in actions
        assert "update_base_url" in actions

    @pytest.mark.asyncio
    async def test_migration_guide_missing_version(self, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(db_session)
        tracker = DeprecationTracker(db_session)

        guide = await tracker.get_migration_guide(adapter.id, "v1", "v99")

        assert "error" in guide
        assert guide["steps"] == []

    @pytest.mark.asyncio
    async def test_migration_guide_includes_changelog(self, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(db_session)
        tracker = DeprecationTracker(db_session)

        guide = await tracker.get_migration_guide(adapter.id, "v1", "v2")

        actions = [s["action"] for s in guide["steps"]]
        assert "review_changelog" in actions


class TestSunsetDateComputation:
    def test_sunset_date_uses_default_window(self) -> None:
        from unittest.mock import MagicMock

        now = datetime.now(UTC)
        version = MagicMock(spec=["updated_at"])
        version.updated_at = now

        sunset = DeprecationTracker._compute_sunset_date(version)

        assert sunset is not None
        expected = now + timedelta(days=DEFAULT_SUNSET_DAYS)
        assert abs((sunset - expected).total_seconds()) < 1

    def test_sunset_date_none_when_no_updated_at(self) -> None:
        from unittest.mock import MagicMock

        version = MagicMock(spec=["updated_at"])
        version.updated_at = None

        sunset = DeprecationTracker._compute_sunset_date(version)
        assert sunset is None


# ---------------------------------------------------------------------------
# Tests: API Endpoint
# ---------------------------------------------------------------------------


class TestDeprecationEndpoint:
    @pytest.mark.asyncio
    async def test_deprecated_version_endpoint(self, client, db_session: AsyncSession) -> None:
        adapter, v1, v2 = await _seed_adapter_with_versions(db_session)
        await db_session.commit()

        resp = await client.get(f"/api/v1/adapters/{adapter.id}/versions/v1/deprecation")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "deprecated"
        assert data["replacement_version"] == "v2"
        assert data["sunset_date"] is not None
        assert len(data["migration_guide"]) > 0

    @pytest.mark.asyncio
    async def test_active_version_endpoint(self, client, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(db_session)
        await db_session.commit()

        resp = await client.get(f"/api/v1/adapters/{adapter.id}/versions/v2/deprecation")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["days_until_sunset"] is None

    @pytest.mark.asyncio
    async def test_not_found_version_endpoint(self, client, db_session: AsyncSession) -> None:
        adapter, _, _ = await _seed_adapter_with_versions(db_session)
        await db_session.commit()

        resp = await client.get(f"/api/v1/adapters/{adapter.id}/versions/v99/deprecation")

        assert resp.status_code == 404
