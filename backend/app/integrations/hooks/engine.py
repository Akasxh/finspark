"""
Hook engine for the integration adapter system.

Design:
  HookPhase   — enum: PRE_REQUEST | POST_RESPONSE | ON_ERROR
  HookContext — mutable bag passed through the hook chain; hooks can mutate
                payload/result and set abort=True to short-circuit execution
  HookEngine  — per-adapter ordered list of callables, async-aware

Hook callables must have the signature:
    async def my_hook(ctx: HookContext) -> None

Setting ctx.abort = True from any hook stops the chain for that phase.
ON_ERROR hooks receive ctx.error (the live exception) and may suppress it
by setting ctx.error = None.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from enum import Enum
from functools import wraps
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)


class HookPhase(str, Enum):
    PRE_REQUEST = "pre_request"
    POST_RESPONSE = "post_response"
    ON_ERROR = "on_error"


# Callable type — both sync and async are accepted; sync ones are wrapped
HookCallable = Callable[["HookContext"], Coroutine[Any, Any, None] | None]


class HookContext:
    """
    Mutable execution context threaded through a hook chain.

    Attributes:
        adapter_kind    adapter kind string e.g. "credit_bureau"
        adapter_version adapter version string e.g. "v1"
        operation       operation name e.g. "fetch_credit_score"
        payload         the outgoing request payload (mutable)
        result          the incoming response (mutable, None during PRE_REQUEST)
        error           live exception, only set during ON_ERROR phase
        abort           set True to stop processing the current chain
        metadata        free-form dict for hooks to communicate with each other
    """

    __slots__ = (
        "adapter_kind",
        "adapter_version",
        "operation",
        "payload",
        "result",
        "error",
        "abort",
        "metadata",
    )

    def __init__(
        self,
        adapter_kind: str,
        adapter_version: str,
        operation: str,
        payload: dict[str, Any],
    ) -> None:
        self.adapter_kind = adapter_kind
        self.adapter_version = adapter_version
        self.operation = operation
        self.payload: dict[str, Any] = payload
        self.result: dict[str, Any] | None = None
        self.error: BaseException | None = None
        self.abort: bool = False
        self.metadata: dict[str, Any] = {}


class HookEngine:
    """
    Manages ordered hook chains per phase.

    Usage:
        engine = HookEngine()
        engine.register(HookPhase.PRE_REQUEST, log_request_hook, priority=10)
        engine.register(HookPhase.POST_RESPONSE, mask_pii_hook, priority=5)

        ctx = HookContext(...)
        await engine.run(HookPhase.PRE_REQUEST, ctx)
    """

    def __init__(self) -> None:
        # {phase: [(priority, hook_fn)]}  — lower priority int runs first
        self._hooks: defaultdict[HookPhase, list[tuple[int, HookCallable]]] = defaultdict(list)

    def register(
        self,
        phase: HookPhase,
        fn: HookCallable,
        priority: int = 100,
    ) -> None:
        """Register a hook.  Lower priority values execute first."""
        self._hooks[phase].append((priority, fn))
        self._hooks[phase].sort(key=lambda t: t[0])
        fn_name = getattr(fn, "__name__", type(fn).__name__)
        log.debug("Registered hook %s for phase %s (priority=%d)", fn_name, phase, priority)

    def unregister(self, phase: HookPhase, fn: HookCallable) -> bool:
        """Remove a previously registered hook.  Returns True if found."""
        before = len(self._hooks[phase])
        self._hooks[phase] = [(p, f) for p, f in self._hooks[phase] if f is not fn]
        return len(self._hooks[phase]) < before

    async def run(self, phase: HookPhase, ctx: HookContext) -> None:
        """
        Execute all hooks for the given phase in priority order.

        Sync callables are run in the default executor to avoid blocking
        the event loop.
        """
        for _, fn in self._hooks[phase]:
            if ctx.abort:
                log.debug("Hook chain aborted at %s (phase=%s)", fn.__name__, phase)
                break
            fn_name = getattr(fn, "__name__", type(fn).__name__)
            try:
                coro_or_none = fn(ctx)
                if asyncio.iscoroutine(coro_or_none):
                    await coro_or_none
                elif coro_or_none is not None:
                    # Sync callable returned something unexpected — warn and continue
                    log.warning("Hook %s returned non-None, non-coroutine value", fn_name)
            except Exception as exc:  # noqa: BLE001
                log.exception("Hook %s raised during phase %s: %s", fn_name, phase, exc)
                if phase != HookPhase.ON_ERROR:
                    raise


def hook(
    phase: HookPhase,
    engine: HookEngine,
    priority: int = 100,
) -> Callable[[HookCallable], HookCallable]:
    """
    Decorator that registers a function as a hook on *engine*.

    Example::

        @hook(HookPhase.PRE_REQUEST, my_engine, priority=5)
        async def stamp_correlation_id(ctx: HookContext) -> None:
            ctx.payload["x_correlation_id"] = str(uuid.uuid4())
    """

    def decorator(fn: HookCallable) -> HookCallable:
        engine.register(phase, fn, priority=priority)

        @wraps(fn)
        async def wrapper(ctx: HookContext) -> None:
            result = fn(ctx)
            if asyncio.iscoroutine(result):
                await result

        return wrapper

    return decorator
