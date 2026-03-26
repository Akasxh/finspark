"""
Test data factories using factory_boy with SQLAlchemy async models.

Usage:
    tenant = TenantFactory.build()                   # no DB
    tenant = await TenantFactory.create(db_session)  # persists

All factories are self-contained and don't require factory_boy to be
installed at collection time — they fall back to simple dataclass builders.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Factory base (factory_boy if available, else pure-Python fallback)
# ---------------------------------------------------------------------------

try:
    import factory  # type: ignore[import]
    from factory import LazyFunction, Sequence, SubFactory  # type: ignore[import]

    FACTORY_BOY_AVAILABLE = True
except ImportError:
    FACTORY_BOY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Pure-Python fallback factories (always available)
# ---------------------------------------------------------------------------


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TenantData:
    id: str = field(default_factory=_uuid)
    name: str = "Test Corp"
    slug: str = field(default_factory=lambda: f"test-corp-{uuid.uuid4().hex[:8]}")
    plan: str = "enterprise"
    is_active: bool = True
    created_at: datetime = field(default_factory=_now)


@dataclass
class AdapterData:
    id: str = field(default_factory=_uuid)
    name: str = "CIBIL Bureau"
    slug: str = "cibil-bureau"
    category: str = "credit_bureau"
    versions: list[str] = field(default_factory=lambda: ["1.0", "2.0"])
    latest_version: str = "2.0"
    is_active: bool = True


@dataclass
class IntegrationData:
    id: str = field(default_factory=_uuid)
    tenant_id: str = field(default_factory=_uuid)
    adapter_slug: str = "cibil-bureau"
    adapter_version: str = "2.0"
    name: str = "Credit Check"
    config: dict[str, Any] = field(
        default_factory=lambda: {
            "base_url": "https://api.cibil.example.com",
            "timeout_ms": 3000,
            "retry_count": 3,
        }
    )
    is_active: bool = True


@dataclass
class FieldMappingData:
    id: str = field(default_factory=_uuid)
    tenant_id: str = field(default_factory=_uuid)
    adapter_slug: str = "cibil-bureau"
    source_field: str = "customer.pan"
    target_field: str = "bureau.pan_number"
    transform: str | None = None
    is_required: bool = True


# ---------------------------------------------------------------------------
# factory_boy factories (only when package is installed)
# ---------------------------------------------------------------------------

if FACTORY_BOY_AVAILABLE:
    try:
        from app.db.models.tenant import Tenant  # type: ignore[import]
        from app.db.models.adapter import Adapter  # type: ignore[import]
        from app.db.models.integration import Integration  # type: ignore[import]
        from app.db.models.mapping import FieldMapping  # type: ignore[import]

        class TenantFactory(factory.Factory):  # type: ignore[misc]
            class Meta:
                model = Tenant

            id = factory.LazyFunction(_uuid)
            name = factory.Sequence(lambda n: f"Corp {n}")
            slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
            plan = "enterprise"
            is_active = True

        class AdapterFactory(factory.Factory):  # type: ignore[misc]
            class Meta:
                model = Adapter

            id = factory.LazyFunction(_uuid)
            name = factory.Sequence(lambda n: f"Adapter {n}")
            slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))
            category = "credit_bureau"
            latest_version = "2.0"
            is_active = True

        class IntegrationFactory(factory.Factory):  # type: ignore[misc]
            class Meta:
                model = Integration

            id = factory.LazyFunction(_uuid)
            tenant_id = factory.LazyFunction(_uuid)
            adapter_slug = "cibil-bureau"
            adapter_version = "2.0"
            name = factory.Sequence(lambda n: f"Integration {n}")
            is_active = True

        class FieldMappingFactory(factory.Factory):  # type: ignore[misc]
            class Meta:
                model = FieldMapping

            id = factory.LazyFunction(_uuid)
            tenant_id = factory.LazyFunction(_uuid)
            adapter_slug = "cibil-bureau"
            source_field = "customer.pan"
            target_field = "bureau.pan_number"
            transform = None
            is_required = True

    except ImportError:
        pass  # ORM models not yet written; factories still usable via TenantData etc.


# ---------------------------------------------------------------------------
# Tests for the fallback factories
# ---------------------------------------------------------------------------


class TestTenantFactory:
    def test_build_has_unique_ids(self) -> None:
        t1 = TenantData()
        t2 = TenantData()
        assert t1.id != t2.id

    def test_build_defaults(self) -> None:
        t = TenantData()
        assert t.is_active is True
        assert t.plan == "enterprise"

    def test_override_fields(self) -> None:
        t = TenantData(name="Rival Corp", plan="standard", is_active=False)
        assert t.name == "Rival Corp"
        assert t.plan == "standard"
        assert t.is_active is False


class TestAdapterFactory:
    def test_default_versions(self) -> None:
        a = AdapterData()
        assert "2.0" in a.versions
        assert a.latest_version == "2.0"

    def test_category_field(self) -> None:
        a = AdapterData(category="kyc")
        assert a.category == "kyc"


class TestIntegrationFactory:
    def test_config_structure(self) -> None:
        i = IntegrationData()
        assert "base_url" in i.config
        assert i.config["timeout_ms"] == 3000

    def test_different_tenant_ids(self) -> None:
        i1 = IntegrationData()
        i2 = IntegrationData()
        assert i1.tenant_id != i2.tenant_id


class TestFieldMappingFactory:
    def test_required_flag(self) -> None:
        m = FieldMappingData()
        assert m.is_required is True

    def test_transform_nullable(self) -> None:
        m = FieldMappingData(transform="iso8601_date")
        assert m.transform == "iso8601_date"


# ---------------------------------------------------------------------------
# Async factory helpers (for integration tests)
# ---------------------------------------------------------------------------


async def create_tenant(session: Any, **kwargs: Any) -> Any:
    """
    Helper for integration tests: insert a Tenant and flush.
    Returns the ORM object.
    """
    from app.db.models.tenant import Tenant  # type: ignore[import]

    data = {**TenantData().__dict__, **kwargs}
    obj = Tenant(**data)
    session.add(obj)
    await session.flush()
    return obj


async def create_adapter(session: Any, **kwargs: Any) -> Any:
    from app.db.models.adapter import Adapter  # type: ignore[import]

    data = {**AdapterData().__dict__, **kwargs}
    obj = Adapter(**data)
    session.add(obj)
    await session.flush()
    return obj


async def create_integration(session: Any, tenant_id: str, **kwargs: Any) -> Any:
    from app.db.models.integration import Integration  # type: ignore[import]

    data = {**IntegrationData().__dict__, "tenant_id": tenant_id, **kwargs}
    obj = Integration(**data)
    session.add(obj)
    await session.flush()
    return obj
