"""
Rollback mechanism for IntegrationConfig changes.

Workflow:
1. `ConfigSnapshot.capture(config)` — deep-copies the current config.
2. Apply changes to the live config.
3. Run simulation; if it fails, call `snapshot.restore()` to revert.
4. All snapshots are immutable once created.

Thread-safety: snapshots are plain Pydantic models; restoring replaces the
mutable `IntegrationConfig` fields in-place.  Callers are responsible for
locking if configs are shared across async tasks.
"""
from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from finspark.simulation.types import FieldMapping, IntegrationConfig


class ConfigSnapshot(BaseModel):
    """Immutable point-in-time snapshot of an IntegrationConfig."""

    snapshot_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    config_id: str
    tenant_id: str
    adapter_id: str
    adapter_version: str
    enabled: bool
    settings: dict[str, Any]
    field_overrides: list[FieldMapping]

    @classmethod
    def capture(cls, config: IntegrationConfig) -> "ConfigSnapshot":
        """Deep-copy the current state of *config* into a new snapshot."""
        return cls(
            config_id=config.config_id,
            tenant_id=config.tenant_id,
            adapter_id=config.adapter_id,
            adapter_version=config.adapter_version,
            enabled=config.enabled,
            settings=copy.deepcopy(config.settings),
            field_overrides=copy.deepcopy(config.field_overrides),
        )

    def restore(self, config: IntegrationConfig) -> None:
        """
        Revert *config* in-place to the state captured in this snapshot.
        Raises ValueError if the config_id / tenant_id do not match.
        """
        if config.config_id != self.config_id:
            raise ValueError(
                f"Cannot restore: snapshot.config_id={self.config_id} "
                f"!= config.config_id={config.config_id}"
            )
        if config.tenant_id != self.tenant_id:
            raise ValueError(
                f"Cannot restore: snapshot.tenant_id={self.tenant_id} "
                f"!= config.tenant_id={config.tenant_id}"
            )

        config.adapter_version = self.adapter_version
        config.enabled = self.enabled
        config.settings = copy.deepcopy(self.settings)
        config.field_overrides = copy.deepcopy(self.field_overrides)
        config.updated_at = datetime.now(UTC)


class RollbackManager:
    """
    Manages a stack of snapshots for a single IntegrationConfig.

    Typical usage:
        manager = RollbackManager(config)
        with manager.transaction() as snapshot:
            config.settings["new_key"] = "value"
            # ... run simulation — raises on failure ...
        # if simulation raises, the context manager rolls back automatically
    """

    def __init__(self, config: IntegrationConfig) -> None:
        self._config = config
        self._stack: list[ConfigSnapshot] = []

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def push_snapshot(self) -> ConfigSnapshot:
        """Capture current state and push onto the stack."""
        snap = ConfigSnapshot.capture(self._config)
        self._stack.append(snap)
        return snap

    def rollback(self) -> ConfigSnapshot:
        """
        Pop the most-recent snapshot and restore it.
        Raises IndexError if there are no snapshots.
        """
        snap = self._stack.pop()
        snap.restore(self._config)
        return snap

    def commit(self) -> None:
        """Discard the most-recent snapshot (change is accepted)."""
        if not self._stack:
            raise IndexError("No snapshot to commit")
        self._stack.pop()

    @property
    def depth(self) -> int:
        return len(self._stack)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    class _Transaction:
        def __init__(self, manager: "RollbackManager") -> None:
            self._manager = manager
            self.snapshot: ConfigSnapshot | None = None

        def __enter__(self) -> "RollbackManager._Transaction":
            self.snapshot = self._manager.push_snapshot()
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
            if exc_type is not None:
                self._manager.rollback()
            else:
                self._manager.commit()
            return False  # never suppress exceptions

    def transaction(self) -> "_Transaction":
        return self._Transaction(self)
