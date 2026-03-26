"""Configuration rollback manager - snapshot, restore, and compare versions."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.configuration import Configuration, ConfigurationHistory
from finspark.schemas.configurations import (
    ConfigHistoryEntry,
    VersionComparisonResponse,
)
from finspark.services.config_engine.diff_engine import ConfigDiffEngine


class RollbackManager:
    """Manages configuration version snapshots and rollbacks."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._diff_engine = ConfigDiffEngine()

    async def snapshot(
        self,
        config_id: str,
        tenant_id: str,
        *,
        change_type: str = "updated",
        changed_by: str | None = None,
    ) -> ConfigurationHistory:
        """Create a ConfigurationHistory entry capturing the current state."""
        config = await self._get_config(config_id, tenant_id)

        current_state = self._serialise_config(config)

        # Fetch the latest history entry to record previous_value
        prev_stmt = (
            select(ConfigurationHistory)
            .where(
                ConfigurationHistory.configuration_id == config_id,
                ConfigurationHistory.tenant_id == tenant_id,
            )
            .order_by(ConfigurationHistory.version.desc())
            .limit(1)
        )
        prev_result = await self._db.execute(prev_stmt)
        prev_entry = prev_result.scalar_one_or_none()

        previous_value = prev_entry.new_value if prev_entry else None

        new_version = (prev_entry.version + 1) if prev_entry else 1

        history = ConfigurationHistory(
            tenant_id=tenant_id,
            configuration_id=config_id,
            version=new_version,
            change_type=change_type,
            previous_value=previous_value,
            new_value=json.dumps(current_state),
            changed_by=changed_by,
        )
        self._db.add(history)
        await self._db.flush()
        return history

    async def rollback(
        self,
        config_id: str,
        target_version: int,
        tenant_id: str,
        *,
        changed_by: str | None = None,
    ) -> Configuration:
        """Restore a configuration to a specific historical version."""
        config = await self._get_config(config_id, tenant_id)

        # Fetch the target history entry
        target_stmt = select(ConfigurationHistory).where(
            ConfigurationHistory.configuration_id == config_id,
            ConfigurationHistory.tenant_id == tenant_id,
            ConfigurationHistory.version == target_version,
        )
        target_result = await self._db.execute(target_stmt)
        target_entry = target_result.scalar_one_or_none()
        if not target_entry:
            raise ValueError(f"Version {target_version} not found for configuration {config_id}")

        if not target_entry.new_value:
            raise ValueError(f"Version {target_version} has no saved state to restore")

        snapshot_data: dict[str, Any] = json.loads(target_entry.new_value)

        # Save current state as a snapshot before overwriting
        await self.snapshot(
            config_id,
            tenant_id,
            change_type="pre_rollback",
            changed_by=changed_by,
        )

        previous_version = config.version

        # Apply restored state
        config.field_mappings = json.dumps(snapshot_data.get("field_mappings"))
        config.transformation_rules = json.dumps(snapshot_data.get("transformation_rules"))
        config.hooks = json.dumps(snapshot_data.get("hooks"))
        config.auth_config = (
            json.dumps(snapshot_data.get("auth_config"))
            if snapshot_data.get("auth_config")
            else None
        )
        config.full_config = json.dumps(snapshot_data.get("full_config"))
        config.status = "rollback"
        config.version = previous_version + 1

        # Record rollback in history
        rollback_history = ConfigurationHistory(
            tenant_id=tenant_id,
            configuration_id=config_id,
            version=config.version,
            change_type="rollback",
            previous_value=None,
            new_value=json.dumps(self._serialise_config(config)),
            changed_by=changed_by,
        )
        self._db.add(rollback_history)
        await self._db.flush()

        return config

    async def list_versions(
        self,
        config_id: str,
        tenant_id: str,
    ) -> list[ConfigHistoryEntry]:
        """Return the full version history for a configuration."""
        stmt = (
            select(ConfigurationHistory)
            .where(
                ConfigurationHistory.configuration_id == config_id,
                ConfigurationHistory.tenant_id == tenant_id,
            )
            .order_by(ConfigurationHistory.version.asc())
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        return [
            ConfigHistoryEntry(
                id=row.id,
                configuration_id=row.configuration_id,
                version=row.version,
                change_type=row.change_type,
                previous_value=json.loads(row.previous_value) if row.previous_value else None,
                new_value=json.loads(row.new_value) if row.new_value else None,
                changed_by=row.changed_by,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def compare_versions(
        self,
        config_id: str,
        version_a: int,
        version_b: int,
        tenant_id: str,
    ) -> VersionComparisonResponse:
        """Diff two versions of the same configuration."""
        stmt = select(ConfigurationHistory).where(
            ConfigurationHistory.configuration_id == config_id,
            ConfigurationHistory.tenant_id == tenant_id,
            ConfigurationHistory.version.in_([version_a, version_b]),
        )
        result = await self._db.execute(stmt)
        entries = {row.version: row for row in result.scalars().all()}

        if version_a not in entries:
            raise ValueError(f"Version {version_a} not found for configuration {config_id}")
        if version_b not in entries:
            raise ValueError(f"Version {version_b} not found for configuration {config_id}")

        state_a: dict[str, Any] = (
            json.loads(entries[version_a].new_value) if entries[version_a].new_value else {}
        )
        state_b: dict[str, Any] = (
            json.loads(entries[version_b].new_value) if entries[version_b].new_value else {}
        )

        diff_result = self._diff_engine.compare(
            state_a,
            state_b,
            config_a_id=f"v{version_a}",
            config_b_id=f"v{version_b}",
        )

        return VersionComparisonResponse(
            configuration_id=config_id,
            version_a=version_a,
            version_b=version_b,
            total_changes=diff_result.total_changes,
            breaking_changes=diff_result.breaking_changes,
            diffs=diff_result.diffs,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_config(self, config_id: str, tenant_id: str) -> Configuration:
        stmt = select(Configuration).where(
            Configuration.id == config_id,
            Configuration.tenant_id == tenant_id,
        )
        result = await self._db.execute(stmt)
        config = result.scalar_one_or_none()
        if not config:
            raise ValueError(f"Configuration {config_id} not found")
        return config

    @staticmethod
    def _serialise_config(config: Configuration) -> dict[str, Any]:
        return {
            "field_mappings": json.loads(config.field_mappings) if config.field_mappings else None,
            "transformation_rules": json.loads(config.transformation_rules)
            if config.transformation_rules
            else None,
            "hooks": json.loads(config.hooks) if config.hooks else None,
            "auth_config": json.loads(config.auth_config) if config.auth_config else None,
            "full_config": json.loads(config.full_config) if config.full_config else None,
            "status": config.status,
            "version": config.version,
        }
