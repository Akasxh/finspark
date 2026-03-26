"""In-memory rate limiter and metrics middleware."""

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response


class _TokenBucket:
    """Simple per-tenant sliding-window request counter."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, tenant_id: str) -> tuple[bool, int]:
        """Check if a request is allowed. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[tenant_id]
            # Prune expired entries
            self._requests[tenant_id] = [t for t in timestamps if t > cutoff]
            timestamps = self._requests[tenant_id]

            if len(timestamps) >= self.max_requests:
                oldest = min(timestamps)
                retry_after = int(oldest - cutoff) + 1
                return False, max(retry_after, 1)

            timestamps.append(now)
            return True, 0

    def reset(self) -> None:
        """Clear all tracked requests (useful for testing)."""
        with self._lock:
            self._requests.clear()


class MetricsCollector:
    """Simple in-memory metrics collector."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.total_requests: int = 0
        self.requests_per_endpoint: dict[str, int] = defaultdict(int)
        self.total_response_time: float = 0.0
        self.active_tenants: set[str] = set()

    def record(self, path: str, tenant_id: str, response_time_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            self.requests_per_endpoint[path] += 1
            self.total_response_time += response_time_ms
            self.active_tenants.add(tenant_id)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
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

    def reset(self) -> None:
        with self._lock:
            self.total_requests = 0
            self.requests_per_endpoint.clear()
            self.total_response_time = 0.0
            self.active_tenants.clear()


# Module-level singletons
rate_limiter = _TokenBucket()
metrics = MetricsCollector()


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Enforces per-tenant request rate limits."""

    # Paths that bypass rate limiting
    EXEMPT_PATHS: set[str] = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", "unknown")
        allowed, retry_after = rate_limiter.is_allowed(tenant_id)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please retry later."},
                headers={"Retry-After": str(retry_after)},
            )

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        metrics.record(request.url.path, tenant_id, duration_ms)
        return response
