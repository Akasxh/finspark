"""
AdapterRegistry — central discovery and instantiation hub.

Design:
  - Single global instance (singleton via module-level _REGISTRY).
  - Adapters are keyed by (kind, version) tuples.
  - Multiple versions of the same kind can coexist.
  - register_adapter() is a class decorator for explicit registration;
    BaseAdapter.__init_subclass__ handles auto_register=True adapters.
  - get() returns a *fresh* configured adapter instance; it does NOT cache
    instances because config is caller-supplied (multi-tenant).
  - discover() returns metadata for all registered adapters — used by the
    auto-configuration engine to enumerate available integrations.

Thread safety: registration is module-import-time; no mutation after boot.
Concurrent reads are safe on CPython (dict read is atomic).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.integrations.config import validate_config
from app.integrations.metadata import AdapterMetadata
from app.integrations.types import AdapterVersion

if TYPE_CHECKING:
    from app.integrations.base import BaseAdapter
    from app.integrations.config import AdapterConfig

log = logging.getLogger(__name__)

_AdapterKey = tuple[str, str]   # (kind, version)


class AdapterRegistry:
    """
    Central registry of integration adapters.

    Usage::

        registry = get_registry()

        # Discover what's available
        for meta in registry.discover():
            print(meta.display_name, meta.version)

        # Instantiate a specific adapter
        adapter = registry.get(
            kind="credit_bureau",
            version="v1",
            config_raw={"api_key": "...", "member_id": "..."},
        )
        await adapter.connect()
        result = await adapter.execute("fetch_score", {"pan": "ABCDE1234F"})
    """

    def __init__(self) -> None:
        self._classes: dict[_AdapterKey, type[BaseAdapter]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register_class(self, cls: type[BaseAdapter]) -> None:
        """Internal — called by BaseAdapter.__init_subclass__ and register_adapter."""
        key: _AdapterKey = (cls.metadata.kind, cls.metadata.version)
        if key in self._classes:
            existing = self._classes[key].__name__
            raise RuntimeError(
                f"Adapter conflict: key {key!r} already registered by {existing!r}. "
                f"Cannot register {cls.__name__!r} again."
            )
        self._classes[key] = cls
        log.info("Registered adapter %s as %s:%s", cls.__name__, *key)

    def register(self, cls: type[BaseAdapter]) -> type[BaseAdapter]:
        """Explicit registration — usable as a class decorator."""
        self._register_class(cls)
        return cls

    def unregister(self, kind: str, version: str) -> bool:
        """Remove an adapter registration (useful in tests).  Returns True if found."""
        key = (kind, version)
        if key in self._classes:
            del self._classes[key]
            log.info("Unregistered adapter %s:%s", kind, version)
            return True
        return False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(
        self,
        kind: str | None = None,
        version: str | None = None,
    ) -> list[AdapterMetadata]:
        """
        Return metadata for all registered adapters, optionally filtered.

        Args:
            kind:     filter to a specific adapter kind (e.g. "credit_bureau")
            version:  filter to a specific version (e.g. "v1")
        """
        results: list[AdapterMetadata] = []
        for (k, v), cls in self._classes.items():
            if kind is not None and k != kind:
                continue
            if version is not None and v != version:
                continue
            results.append(cls.metadata)
        return sorted(results, key=lambda m: (m.kind, m.version))

    def list_kinds(self) -> list[str]:
        """Return unique adapter kinds registered."""
        return sorted({k for k, _ in self._classes})

    def list_versions(self, kind: str) -> list[str]:
        """Return all registered versions for a given kind."""
        return sorted(
            (v for k, v in self._classes if k == kind),
            key=lambda v: (v != AdapterVersion.V1, v),  # v1 before v2 etc.
        )

    def latest_version(self, kind: str) -> str | None:
        """Return the lexicographically latest version for *kind*, or None."""
        versions = self.list_versions(kind)
        return versions[-1] if versions else None

    def has(self, kind: str, version: str) -> bool:
        return (kind, version) in self._classes

    # ------------------------------------------------------------------
    # Instantiation
    # ------------------------------------------------------------------

    def get(
        self,
        kind: str,
        version: str,
        config_raw: dict[str, Any],
    ) -> BaseAdapter:
        """
        Validate config and return a new adapter instance.

        Args:
            kind:       adapter kind string
            version:    adapter version string
            config_raw: raw config dict (will be validated via pydantic)

        Raises:
            KeyError:        if (kind, version) is not registered
            pydantic.ValidationError: if config_raw fails validation
        """
        key: _AdapterKey = (kind, version)
        cls = self._classes.get(key)
        if cls is None:
            available = [f"{k}:{v}" for k, v in sorted(self._classes)]
            raise KeyError(
                f"No adapter registered for {kind!r}:{version!r}. "
                f"Available: {available}"
            )
        config: AdapterConfig = validate_config(kind, version, config_raw)
        return cls(config)

    def get_latest(self, kind: str, config_raw: dict[str, Any]) -> BaseAdapter:
        """Convenience: instantiate the latest registered version of *kind*."""
        version = self.latest_version(kind)
        if version is None:
            raise KeyError(f"No adapters registered for kind {kind!r}")
        return self.get(kind, version, config_raw)

    def __len__(self) -> int:
        return len(self._classes)

    def __repr__(self) -> str:
        keys = [f"{k}:{v}" for k, v in sorted(self._classes)]
        return f"<AdapterRegistry [{', '.join(keys)}]>"


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_REGISTRY = AdapterRegistry()


def get_registry() -> AdapterRegistry:
    """Return the global AdapterRegistry instance."""
    return _REGISTRY


def register_adapter(cls: type[BaseAdapter]) -> type[BaseAdapter]:
    """
    Class decorator for explicit registration.

    Use this when auto_register=True is not appropriate (e.g. third-party
    adapters loaded as plugins after boot).

    Example::

        @register_adapter
        class MyCustomAdapter(BaseAdapter):
            ...
    """
    _REGISTRY._register_class(cls)   # noqa: SLF001
    return cls
