"""In-memory rate limiter and metrics middleware."""

import asyncio
import re
import time
from collections import OrderedDict, defaultdict
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

_MAX_TENANTS = 10_000
_UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def _normalize_path(path: str) -> str:
    """Replace UUIDs in URL paths with {id} to avoid unbounded cardinality."""
    return _UUID_PATTERN.sub("{id}", path)


class _TokenBucket:
    """Simple per-tenant sliding-window request counter with bounded tenant set."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def is_allowed(self, tenant_id: str) -> tuple[bool, int]:
        """Check if a request is allowed. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            if tenant_id in self._requests:
                self._requests.move_to_end(tenant_id)
            else:
                # Evict oldest tenant if at capacity
                if len(self._requests) >= _MAX_TENANTS:
                    self._requests.popitem(last=False)
                self._requests[tenant_id] = []

            timestamps = self._requests[tenant_id]
            self._requests[tenant_id] = [t for t in timestamps if t > cutoff]
            timestamps = self._requests[tenant_id]

            if len(timestamps) >= self.max_requests:
                oldest = min(timestamps)
                retry_after = int(oldest - cutoff) + 1
                return False, max(retry_after, 1)

            timestamps.append(now)
            return True, 0

    async def reset(self) -> None:
        """Clear all tracked requests (useful for testing)."""
        async with self._lock:
            self._requests.clear()


class MetricsCollector:
    """Simple in-memory metrics collector with bounded collections."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.total_requests: int = 0
        self.requests_per_endpoint: dict[str, int] = defaultdict(int)
        self.total_response_time: float = 0.0
        self.active_tenants: OrderedDict[str, None] = OrderedDict()

    async def record(self, path: str, tenant_id: str, response_time_ms: float) -> None:
        normalized = _normalize_path(path)
        async with self._lock:
            self.total_requests += 1
            self.requests_per_endpoint[normalized] += 1
            self.total_response_time += response_time_ms
            # Cap active_tenants at _MAX_TENANTS
            if tenant_id in self.active_tenants:
                self.active_tenants.move_to_end(tenant_id)
            else:
                if len(self.active_tenants) >= _MAX_TENANTS:
                    self.active_tenants.popitem(last=False)
                self.active_tenants[tenant_id] = None

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            avg_response_time = (
                round(self.total_response_time / self.total_requests, 2)
                if self.total_requests > 0
                else 0.0
            )
            return {
                "total_requests": self.total_requests,
                "requests_per_endpoint": dict(self.requests_per_endpoint),
                "avg_response_time_ms": avg_response_time,
                "active_tenants": len(self.active_tenants),
            }

    async def reset(self) -> None:
        async with self._lock:
            self.total_requests = 0
            self.requests_per_endpoint.clear()
            self.total_response_time = 0.0
            self.active_tenants.clear()


# Module-level singletons — initialised from settings
def _create_rate_limiter() -> _TokenBucket:
    from finspark.core.config import settings

    return _TokenBucket(
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


rate_limiter = _create_rate_limiter()
metrics = MetricsCollector()


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Enforces per-tenant request rate limits."""

    EXEMPT_PATHS: set[str] = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", "unknown")
        allowed, retry_after = await rate_limiter.is_allowed(tenant_id)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please retry later."},
                headers={"Retry-After": str(retry_after)},
            )

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        await metrics.record(request.url.path, tenant_id, duration_ms)
        return response
