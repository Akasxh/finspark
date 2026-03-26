"""
Built-in hook implementations that ship with the registry.

These are intentionally generic and adapter-agnostic.  Adapters attach them
via HookEngine.register() in their __init_subclass__ or setup() method.

Available hooks:
  log_request_hook          — structured log of outgoing payload
  log_response_hook         — structured log of incoming result
  pii_mask_hook             — redacts PAN / Aadhaar / mobile numbers in logs
  rate_limit_guard_hook     — raises if request rate exceeds adapter metadata
  correlation_id_hook       — injects x_correlation_id into payload metadata
  retry_on_transient_hook   — marks ctx for retry on 5xx / network errors
  error_to_result_hook      — swallows known errors and returns structured error result
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections import deque
from typing import Any

from app.integrations.hooks.engine import HookContext, HookPhase  # noqa: F401 (re-export hint)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII patterns (Indian fintech context)
# ---------------------------------------------------------------------------
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR_RE = re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b")
_MOBILE_RE = re.compile(r"\b[6-9]\d{9}\b")
_ACCOUNT_RE = re.compile(r"\b\d{9,18}\b")


def _mask_str(s: str) -> str:
    s = _PAN_RE.sub(lambda m: m.group()[:2] + "XXXXX" + m.group()[-1], s)
    s = _AADHAAR_RE.sub("XXXX-XXXX-XXXX", s)
    s = _MOBILE_RE.sub("XXXXXXXXXX", s)
    return s


def _deep_mask(obj: Any, depth: int = 0) -> Any:
    if depth > 8:
        return obj
    if isinstance(obj, str):
        return _mask_str(obj)
    if isinstance(obj, dict):
        return {k: _deep_mask(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_mask(i, depth + 1) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# Hook implementations
# ---------------------------------------------------------------------------

async def log_request_hook(ctx: HookContext) -> None:
    log.info(
        "adapter_request",
        extra={
            "adapter": f"{ctx.adapter_kind}:{ctx.adapter_version}",
            "operation": ctx.operation,
            "payload_keys": list(ctx.payload.keys()),
        },
    )


async def log_response_hook(ctx: HookContext) -> None:
    if ctx.result is not None:
        log.info(
            "adapter_response",
            extra={
                "adapter": f"{ctx.adapter_kind}:{ctx.adapter_version}",
                "operation": ctx.operation,
                "result_keys": list(ctx.result.keys()),
            },
        )


async def pii_mask_hook(ctx: HookContext) -> None:
    """Redacts PAN / Aadhaar / mobile numbers before the payload leaves the process."""
    ctx.payload = _deep_mask(ctx.payload)


async def correlation_id_hook(ctx: HookContext) -> None:
    """Stamps a UUID correlation ID onto every outgoing payload."""
    ctx.payload.setdefault("x_correlation_id", str(uuid.uuid4()))
    ctx.metadata["correlation_id"] = ctx.payload["x_correlation_id"]


async def error_to_result_hook(ctx: HookContext) -> None:
    """
    ON_ERROR hook: wraps the exception into a structured result dict so
    callers always get a dict back, never a raw exception.
    """
    if ctx.error is not None:
        ctx.result = {
            "success": False,
            "error_type": type(ctx.error).__name__,
            "error_message": str(ctx.error),
            "adapter": f"{ctx.adapter_kind}:{ctx.adapter_version}",
            "operation": ctx.operation,
        }
        log.error(
            "adapter_error",
            extra={
                "adapter": f"{ctx.adapter_kind}:{ctx.adapter_version}",
                "operation": ctx.operation,
                "error": str(ctx.error),
            },
        )
        ctx.error = None   # suppressed — result carries the error info


class RateLimitGuard:
    """
    Sliding-window rate limiter that can be registered as a PRE_REQUEST hook.

    Instantiate once per adapter; the instance is callable and async.

        guard = RateLimitGuard(requests_per_second=5.0, burst_size=10)
        engine.register(HookPhase.PRE_REQUEST, guard, priority=1)
    """

    def __init__(self, requests_per_second: float, burst_size: int = 10) -> None:
        self._rps = requests_per_second
        self._burst = burst_size
        self._timestamps: deque[float] = deque()

    async def __call__(self, ctx: HookContext) -> None:
        now = time.monotonic()
        window = 1.0 / self._rps if self._rps > 0 else float("inf")
        cutoff = now - window * self._burst
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self._burst:
            wait = (self._timestamps[0] + window * self._burst) - now
            raise RuntimeError(
                f"Rate limit exceeded for {ctx.adapter_kind}:{ctx.adapter_version}. "
                f"Retry after {wait:.2f}s."
            )
        self._timestamps.append(now)
