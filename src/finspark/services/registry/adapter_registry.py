"""Adapter registry service - manages integration adapters and versions."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finspark.models.adapter import Adapter, AdapterVersion


class AdapterRegistry:
    """Manages the catalog of pre-built integration adapters."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_adapters(
        self,
        category: str | None = None,
        is_active: bool = True,
    ) -> list[Adapter]:
        stmt = select(Adapter).options(selectinload(Adapter.versions))
        if category:
            stmt = stmt.where(Adapter.category == category)
        if is_active:
            stmt = stmt.where(Adapter.is_active == True)  # noqa: E712
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_adapter(self, adapter_id: str) -> Adapter | None:
        stmt = (
            select(Adapter).options(selectinload(Adapter.versions)).where(Adapter.id == adapter_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_adapter_version(self, version_id: str) -> AdapterVersion | None:
        stmt = select(AdapterVersion).where(AdapterVersion.id == version_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_adapter_by_name(self, name: str) -> Adapter | None:
        stmt = select(Adapter).options(selectinload(Adapter.versions)).where(Adapter.name == name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_adapter(
        self,
        name: str,
        category: str,
        description: str = "",
        icon: str | None = None,
    ) -> Adapter:
        adapter = Adapter(
            name=name,
            category=category,
            description=description,
            icon=icon,
        )
        self.db.add(adapter)
        await self.db.flush()
        return adapter

    async def add_version(
        self,
        adapter_id: str,
        version: str,
        base_url: str,
        auth_type: str,
        endpoints: list[dict[str, Any]],
        request_schema: dict[str, Any] | None = None,
        response_schema: dict[str, Any] | None = None,
        config_template: dict[str, Any] | None = None,
        changelog: str = "",
    ) -> AdapterVersion:
        # Determine version order
        stmt = (
            select(AdapterVersion)
            .where(AdapterVersion.adapter_id == adapter_id)
            .order_by(AdapterVersion.version_order.desc())
        )
        result = await self.db.execute(stmt)
        latest = result.scalar_one_or_none()
        version_order = (latest.version_order + 1) if latest else 1

        av = AdapterVersion(
            adapter_id=adapter_id,
            version=version,
            version_order=version_order,
            base_url=base_url,
            auth_type=auth_type,
            endpoints=json.dumps(endpoints),
            request_schema=json.dumps(request_schema) if request_schema else None,
            response_schema=json.dumps(response_schema) if response_schema else None,
            config_template=json.dumps(config_template) if config_template else None,
            changelog=changelog,
        )
        self.db.add(av)
        await self.db.flush()
        return av

    async def deprecate_version(self, version_id: str) -> AdapterVersion | None:
        version = await self.get_adapter_version(version_id)
        if version:
            version.status = "deprecated"
            await self.db.flush()
        return version

    async def get_categories(self) -> list[str]:
        stmt = select(Adapter.category).distinct()
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def find_matching_adapters(self, services: list[str]) -> list[Adapter]:
        """Find adapters that match the identified services from document parsing."""
        adapters = await self.list_adapters()
        matched = []
        service_lower = [s.lower() for s in services]

        for adapter in adapters:
            adapter_terms = adapter.name.lower().split() + [adapter.category.lower()]
            if adapter.description:
                adapter_terms.extend(adapter.description.lower().split())

            for service in service_lower:
                if any(term in service or service in term for term in adapter_terms):
                    matched.append(adapter)
                    break

        return matched
