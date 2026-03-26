"""Deprecation tracking for adapter versions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.adapter import AdapterVersion

# Default sunset window: 90 days after deprecation
DEFAULT_SUNSET_DAYS = 90


class DeprecationTracker:
    """Tracks deprecation status, sunset dates, and migration guides for adapter versions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_deprecated_versions(self, adapter_id: str) -> list[dict[str, Any]]:
        """Return all deprecated versions for an adapter with computed sunset dates."""
        stmt = (
            select(AdapterVersion)
            .where(
                AdapterVersion.adapter_id == adapter_id,
                AdapterVersion.status == "deprecated",
            )
            .order_by(AdapterVersion.version_order)
        )
        result = await self.db.execute(stmt)
        versions = list(result.scalars().all())

        deprecated_list: list[dict[str, Any]] = []
        for v in versions:
            sunset_date = self._compute_sunset_date(v)
            deprecated_list.append(
                {
                    "version_id": v.id,
                    "version": v.version,
                    "deprecated_at": v.updated_at.isoformat() if v.updated_at else None,
                    "sunset_date": sunset_date.isoformat() if sunset_date else None,
                    "days_until_sunset": self._days_until(sunset_date),
                }
            )
        return deprecated_list

    async def get_migration_guide(
        self, adapter_id: str, from_version: str, to_version: str
    ) -> dict[str, Any]:
        """Generate migration steps between two adapter versions."""
        stmt = (
            select(AdapterVersion)
            .where(
                AdapterVersion.adapter_id == adapter_id,
                AdapterVersion.version.in_([from_version, to_version]),
            )
            .order_by(AdapterVersion.version_order)
        )
        result = await self.db.execute(stmt)
        versions = {v.version: v for v in result.scalars().all()}

        source = versions.get(from_version)
        target = versions.get(to_version)

        if not source or not target:
            return {
                "error": "One or both versions not found",
                "from_version": from_version,
                "to_version": to_version,
                "steps": [],
            }

        steps = self._build_migration_steps(source, target)
        return {
            "from_version": from_version,
            "to_version": to_version,
            "from_status": source.status,
            "to_status": target.status,
            "steps": steps,
        }

    async def check_version_health(self, adapter_id: str, version_str: str) -> dict[str, Any]:
        """Check health/deprecation status of a specific version."""
        stmt = select(AdapterVersion).where(
            AdapterVersion.adapter_id == adapter_id,
            AdapterVersion.version == version_str,
        )
        result = await self.db.execute(stmt)
        version = result.scalar_one_or_none()

        if not version:
            return {"status": "not_found", "days_until_sunset": None, "replacement_version": None}

        replacement = await self._find_replacement(adapter_id, version)

        if version.status == "deprecated":
            sunset_date = self._compute_sunset_date(version)
            days_left = self._days_until(sunset_date)
            return {
                "status": "deprecated",
                "days_until_sunset": days_left,
                "sunset_date": sunset_date.isoformat() if sunset_date else None,
                "replacement_version": replacement,
            }

        return {
            "status": version.status,
            "days_until_sunset": None,
            "sunset_date": None,
            "replacement_version": replacement if version.status != "active" else None,
        }

    async def _find_replacement(self, adapter_id: str, current: AdapterVersion) -> str | None:
        """Find the next active version with a higher version_order."""
        stmt = (
            select(AdapterVersion)
            .where(
                AdapterVersion.adapter_id == adapter_id,
                AdapterVersion.status == "active",
                AdapterVersion.version_order > current.version_order,
            )
            .order_by(AdapterVersion.version_order)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        replacement = result.scalar_one_or_none()
        return replacement.version if replacement else None

    @staticmethod
    def _compute_sunset_date(version: AdapterVersion) -> datetime | None:
        """Compute sunset date as updated_at + DEFAULT_SUNSET_DAYS."""
        if version.updated_at is None:
            return None
        base = version.updated_at
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        return base + timedelta(days=DEFAULT_SUNSET_DAYS)

    @staticmethod
    def _days_until(target: datetime | None) -> int | None:
        if target is None:
            return None
        now = datetime.now(UTC)
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        delta = (target - now).days
        return max(delta, 0)

    @staticmethod
    def _build_migration_steps(
        source: AdapterVersion, target: AdapterVersion
    ) -> list[dict[str, str]]:
        """Build migration steps by diffing source and target version metadata."""
        steps: list[dict[str, str]] = []

        if source.auth_type != target.auth_type:
            steps.append(
                {
                    "action": "update_auth",
                    "description": (
                        f"Change authentication from '{source.auth_type}' to '{target.auth_type}'"
                    ),
                }
            )

        if source.base_url != target.base_url:
            steps.append(
                {
                    "action": "update_base_url",
                    "description": f"Update base URL from '{source.base_url}' to '{target.base_url}'",
                }
            )

        if source.endpoints != target.endpoints:
            steps.append(
                {
                    "action": "update_endpoints",
                    "description": "Review and update endpoint paths and payloads for the new version",
                }
            )

        if source.request_schema != target.request_schema:
            steps.append(
                {
                    "action": "update_request_schema",
                    "description": "Update request payloads to match the new schema",
                }
            )

        if source.response_schema != target.response_schema:
            steps.append(
                {
                    "action": "update_response_schema",
                    "description": "Update response handling for the new schema",
                }
            )

        if target.changelog:
            steps.append(
                {
                    "action": "review_changelog",
                    "description": f"Review changelog: {target.changelog}",
                }
            )

        if not steps:
            steps.append(
                {
                    "action": "verify",
                    "description": "No breaking changes detected. Verify integration works with new version.",
                }
            )

        return steps
