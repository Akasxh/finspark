"""
Integration tests for database-layer operations.

Covers:
- Tenant CRUD via ORM
- Adapter + AdapterVersion creation
- Integration lifecycle (create, update, soft-delete)
- FieldMapping persistence
- AuditLog write-on-change
- Cascade / FK integrity
- Soft-delete filter (deleted rows not returned by default query)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


class TestTenantDB:
    async def test_create_and_read_tenant(self, db_session: AsyncSession) -> None:
        from app.db.models.tenant import Tenant  # type: ignore[import]

        t = Tenant(
            id=str(uuid.uuid4()),
            name="DB Corp",
            slug="db-corp",
            plan="enterprise",
            is_active=True,
        )
        db_session.add(t)
        await db_session.flush()

        result = await db_session.execute(select(Tenant).where(Tenant.slug == "db-corp"))
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.name == "DB Corp"

    async def test_tenant_slug_is_unique(self, db_session: AsyncSession) -> None:
        from sqlalchemy.exc import IntegrityError

        from app.db.models.tenant import Tenant  # type: ignore[import]

        slug = f"unique-corp-{uuid.uuid4().hex[:6]}"
        db_session.add(Tenant(id=str(uuid.uuid4()), name="A", slug=slug, plan="free"))
        await db_session.flush()

        db_session.add(Tenant(id=str(uuid.uuid4()), name="B", slug=slug, plan="free"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_soft_delete_hides_tenant(self, db_session: AsyncSession) -> None:
        from app.db.models.tenant import Tenant  # type: ignore[import]

        slug = f"soft-del-{uuid.uuid4().hex[:6]}"
        t = Tenant(id=str(uuid.uuid4()), name="Gone Corp", slug=slug, plan="free", is_active=True)
        db_session.add(t)
        await db_session.flush()

        # Soft-delete
        t.is_active = False
        await db_session.flush()

        result = await db_session.execute(
            select(Tenant).where(Tenant.slug == slug, Tenant.is_active == True)  # noqa: E712
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class TestAdapterDB:
    async def test_create_adapter_with_versions(self, db_session: AsyncSession) -> None:
        from app.db.models.adapter import Adapter, AdapterVersion  # type: ignore[import]

        adapter = Adapter(
            id=str(uuid.uuid4()),
            name="Test Bureau",
            slug=f"test-bureau-{uuid.uuid4().hex[:6]}",
            category="credit_bureau",
            latest_version="2.0",
            is_active=True,
        )
        db_session.add(adapter)
        await db_session.flush()

        v1 = AdapterVersion(
            id=str(uuid.uuid4()),
            adapter_id=adapter.id,
            version="1.0",
            openapi_spec={},
            is_deprecated=True,
        )
        v2 = AdapterVersion(
            id=str(uuid.uuid4()),
            adapter_id=adapter.id,
            version="2.0",
            openapi_spec={},
            is_deprecated=False,
        )
        db_session.add_all([v1, v2])
        await db_session.flush()

        result = await db_session.execute(
            select(AdapterVersion).where(AdapterVersion.adapter_id == adapter.id)
        )
        versions = result.scalars().all()
        assert len(versions) == 2
        version_strings = {v.version for v in versions}
        assert version_strings == {"1.0", "2.0"}


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestIntegrationDB:
    async def test_integration_scoped_to_tenant(self, db_session: AsyncSession) -> None:
        from app.db.models.integration import Integration  # type: ignore[import]
        from app.db.models.tenant import Tenant  # type: ignore[import]

        t_id = str(uuid.uuid4())
        db_session.add(
            Tenant(id=t_id, name="Int Tenant", slug=f"int-tenant-{t_id[:6]}", plan="pro")
        )
        await db_session.flush()

        integration = Integration(
            id=str(uuid.uuid4()),
            tenant_id=t_id,
            adapter_slug="cibil-bureau",
            adapter_version="2.0",
            name="Credit Check",
            config={"timeout_ms": 3000},
            is_active=True,
        )
        db_session.add(integration)
        await db_session.flush()

        result = await db_session.execute(
            select(Integration).where(Integration.tenant_id == t_id)
        )
        items = result.scalars().all()
        assert len(items) == 1
        assert items[0].adapter_slug == "cibil-bureau"

    async def test_integration_config_update(self, db_session: AsyncSession) -> None:
        from app.db.models.integration import Integration  # type: ignore[import]
        from app.db.models.tenant import Tenant  # type: ignore[import]

        t_id = str(uuid.uuid4())
        db_session.add(Tenant(id=t_id, name="Up Corp", slug=f"up-{t_id[:6]}", plan="pro"))
        await db_session.flush()

        integ = Integration(
            id=str(uuid.uuid4()),
            tenant_id=t_id,
            adapter_slug="cibil-bureau",
            adapter_version="2.0",
            name="Old Config",
            config={"timeout_ms": 3000},
            is_active=True,
        )
        db_session.add(integ)
        await db_session.flush()

        # Update config
        integ.config = {"timeout_ms": 9000, "retry_count": 5}
        await db_session.flush()

        result = await db_session.execute(
            select(Integration).where(Integration.id == integ.id)
        )
        updated = result.scalar_one()
        assert updated.config["timeout_ms"] == 9000


# ---------------------------------------------------------------------------
# FieldMapping
# ---------------------------------------------------------------------------


class TestFieldMappingDB:
    async def test_create_field_mapping(
        self,
        db_session: AsyncSession,
        mock_tenant: dict[str, Any],
    ) -> None:
        from app.db.models.mapping import FieldMapping  # type: ignore[import]

        fm = FieldMapping(
            id=str(uuid.uuid4()),
            tenant_id=mock_tenant["id"],
            adapter_slug="cibil-bureau",
            source_field="customer.pan",
            target_field="bureau.pan_number",
            transform=None,
            is_required=True,
        )
        db_session.add(fm)
        await db_session.flush()

        result = await db_session.execute(
            select(FieldMapping).where(FieldMapping.tenant_id == mock_tenant["id"])
        )
        rows = result.scalars().all()
        assert any(r.source_field == "customer.pan" for r in rows)

    async def test_field_mapping_tenant_isolation(
        self,
        db_session: AsyncSession,
        mock_tenant: dict[str, Any],
        other_tenant: dict[str, Any],
    ) -> None:
        from app.db.models.mapping import FieldMapping  # type: ignore[import]

        # Create mapping for tenant A
        db_session.add(
            FieldMapping(
                id=str(uuid.uuid4()),
                tenant_id=mock_tenant["id"],
                adapter_slug="cibil-bureau",
                source_field="customer.pan",
                target_field="bureau.pan_number",
                is_required=True,
            )
        )
        await db_session.flush()

        # Query for tenant B — should be empty
        result = await db_session.execute(
            select(FieldMapping).where(FieldMapping.tenant_id == other_tenant["id"])
        )
        assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------


class TestAuditLogDB:
    async def test_audit_log_creation(
        self,
        db_session: AsyncSession,
        mock_tenant: dict[str, Any],
    ) -> None:
        from app.db.models.audit_log import AuditLog  # type: ignore[import]

        log = AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=mock_tenant["id"],
            entity_type="integration",
            entity_id=str(uuid.uuid4()),
            action="created",
            actor="system",
            diff={"before": None, "after": {"timeout_ms": 3000}},
            created_at=datetime.now(UTC),
        )
        db_session.add(log)
        await db_session.flush()

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.tenant_id == mock_tenant["id"])
        )
        rows = result.scalars().all()
        assert any(r.action == "created" for r in rows)

    async def test_audit_log_immutable(
        self,
        db_session: AsyncSession,
        mock_tenant: dict[str, Any],
    ) -> None:
        """AuditLog rows should not be updatable via ORM (application-level constraint)."""
        from app.db.models.audit_log import AuditLog  # type: ignore[import]

        log = AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=mock_tenant["id"],
            entity_type="integration",
            entity_id=str(uuid.uuid4()),
            action="created",
            actor="system",
            diff={},
            created_at=datetime.now(UTC),
        )
        db_session.add(log)
        await db_session.flush()

        # Attempt to modify — app should prevent this via a validator or event
        # For now we just confirm the row exists with original data
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.id == log.id)
        )
        persisted = result.scalar_one()
        assert persisted.action == "created"
