"""
BaseAdapter — abstract base class every integration adapter must subclass.

Contract:
  connect()    — establish / verify connectivity to the external service
  validate()   — validate a payload dict against the adapter's FieldSchema
  transform()  — normalise raw API response into canonical internal format
  execute()    — run the full request lifecycle with hooks

Adapter authors subclass BaseAdapter, implement the four abstract methods,
and declare class-level `metadata: AdapterMetadata` and `Config` type.

__init_subclass__ auto-registers adapters that set `auto_register = True`
(default True) into the global AdapterRegistry.

The hook engine is instantiated per adapter class (not per instance), so
hooks registered via the class-level engine are shared across all instances
of that adapter class.
"""

from __future__ import annotations

import abc
import logging
from typing import Any, ClassVar

from app.integrations.config import AdapterConfig
from app.integrations.hooks.builtin import (
    RateLimitGuard,
    correlation_id_hook,
    error_to_result_hook,
    log_request_hook,
    log_response_hook,
)
from app.integrations.hooks.engine import HookContext, HookEngine, HookPhase
from app.integrations.metadata import AdapterMetadata
from app.integrations.types import AdapterPayload, AdapterResult

log = logging.getLogger(__name__)


class BaseAdapter(abc.ABC):
    """
    Abstract integration adapter.

    Class attributes (must be set by concrete subclasses):
        metadata     AdapterMetadata descriptor
        Config       pydantic config model class

    Instance attributes:
        config       validated AdapterConfig instance
        engine       HookEngine for this adapter class
    """

    metadata: ClassVar[AdapterMetadata]
    Config: ClassVar[type[AdapterConfig]]

    # Set False on abstract intermediate classes to skip auto-registration
    auto_register: ClassVar[bool] = False

    # Class-level hook engine — shared across all instances of this class
    engine: ClassVar[HookEngine]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Only concrete adapters (those with metadata defined) get engines + registration
        if not hasattr(cls, "metadata"):
            return

        # Each concrete subclass gets its own engine so hooks don't bleed across adapters
        cls.engine = HookEngine()

        # Register built-in hooks
        cls.engine.register(HookPhase.PRE_REQUEST, correlation_id_hook, priority=1)
        cls.engine.register(HookPhase.PRE_REQUEST, log_request_hook, priority=10)
        cls.engine.register(HookPhase.POST_RESPONSE, log_response_hook, priority=10)
        cls.engine.register(HookPhase.ON_ERROR, error_to_result_hook, priority=100)

        # Wire rate-limit guard from metadata
        rl = cls.metadata.rate_limit
        guard = RateLimitGuard(
            requests_per_second=rl.requests_per_second,
            burst_size=rl.burst_size,
        )
        cls.engine.register(HookPhase.PRE_REQUEST, guard, priority=2)

        # Auto-register into global registry
        if cls.auto_register:
            from app.integrations.registry.registry import get_registry
            registry = get_registry()
            registry._register_class(cls)  # noqa: SLF001 — intentional internal call

    def __init__(self, config: AdapterConfig) -> None:
        if not isinstance(config, self.Config):
            raise TypeError(
                f"{self.__class__.__name__} expects config of type "
                f"{self.Config.__name__}, got {type(config).__name__}"
            )
        self.config = config

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def connect(self) -> None:
        """
        Establish or verify connectivity to the external service.

        Raise ConnectionError (or a subclass) on failure.
        Should be idempotent — safe to call multiple times.
        """

    @abc.abstractmethod
    def validate(self, payload: AdapterPayload) -> list[str]:
        """
        Validate *payload* against the adapter's FieldSchema definitions.

        Returns a list of error strings (empty list means valid).
        Does NOT raise — callers decide how to handle errors.
        """

    @abc.abstractmethod
    def transform(self, raw_response: dict[str, Any]) -> AdapterResult:
        """
        Normalise the raw API response into the canonical internal format.

        The canonical format always includes:
            success: bool
            adapter: str   (kind:version)
            data: dict     (adapter-specific)
        """

    @abc.abstractmethod
    async def _call(self, payload: AdapterPayload) -> dict[str, Any]:
        """
        Internal method: perform the actual HTTP call (or mock).

        Called by execute() after hooks; not meant to be called directly.
        """

    # ------------------------------------------------------------------
    # Execution lifecycle (hook orchestration)
    # ------------------------------------------------------------------

    async def execute(self, operation: str, payload: AdapterPayload) -> AdapterResult:
        """
        Full lifecycle:
          1. Validate payload
          2. Run PRE_REQUEST hooks
          3. _call() — actual HTTP request
          4. transform() — normalise response
          5. Run POST_RESPONSE hooks
          6. Return result

        On any exception:
          - Runs ON_ERROR hooks
          - If hooks suppress the error (ctx.error = None) returns ctx.result
          - Otherwise re-raises
        """
        errors = self.validate(payload)
        if errors:
            raise ValueError(f"Payload validation failed: {'; '.join(errors)}")

        ctx = HookContext(
            adapter_kind=self.metadata.kind,
            adapter_version=self.metadata.version,
            operation=operation,
            payload=dict(payload),    # defensive copy
        )

        try:
            await self.engine.run(HookPhase.PRE_REQUEST, ctx)
            if ctx.abort:
                return ctx.result or {"success": False, "aborted": True}

            raw = await self._call(ctx.payload)
            ctx.result = self.transform(raw)

            await self.engine.run(HookPhase.POST_RESPONSE, ctx)
            return ctx.result or {}

        except Exception as exc:
            ctx.error = exc
            await self.engine.run(HookPhase.ON_ERROR, ctx)
            if ctx.error is None and ctx.result is not None:
                return ctx.result
            raise

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def is_sandbox(self) -> bool:
        return self.config.sandbox_mode

    @property
    def adapter_id(self) -> str:
        return f"{self.metadata.kind}:{self.metadata.version}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} kind={self.metadata.kind!r} v={self.metadata.version!r} sandbox={self.is_sandbox}>"
