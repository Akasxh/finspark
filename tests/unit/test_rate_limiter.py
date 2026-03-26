"""Tests for rate limiter and metrics."""

import time

import pytest
from httpx import AsyncClient

from finspark.core.rate_limiter import MetricsCollector, _TokenBucket, metrics, rate_limiter


class TestTokenBucket:
    def test_allows_requests_under_limit(self) -> None:
        bucket = _TokenBucket(max_requests=5, window_seconds=60)
        for _ in range(5):
            allowed, _ = bucket.is_allowed("tenant-a")
            assert allowed is True

    def test_blocks_requests_over_limit(self) -> None:
        bucket = _TokenBucket(max_requests=3, window_seconds=60)
        for _ in range(3):
            bucket.is_allowed("tenant-a")

        allowed, retry_after = bucket.is_allowed("tenant-a")
        assert allowed is False
        assert retry_after >= 1

    def test_separate_tenants_tracked_independently(self) -> None:
        bucket = _TokenBucket(max_requests=2, window_seconds=60)
        bucket.is_allowed("tenant-a")
        bucket.is_allowed("tenant-a")

        # tenant-a is exhausted
        allowed, _ = bucket.is_allowed("tenant-a")
        assert allowed is False

        # tenant-b still has quota
        allowed, _ = bucket.is_allowed("tenant-b")
        assert allowed is True

    def test_window_expiry_allows_new_requests(self) -> None:
        bucket = _TokenBucket(max_requests=1, window_seconds=1)
        bucket.is_allowed("t1")

        allowed, _ = bucket.is_allowed("t1")
        assert allowed is False

        # Simulate time passing by manipulating internal timestamps
        with bucket._lock:
            bucket._requests["t1"] = [time.monotonic() - 2]

        allowed, _ = bucket.is_allowed("t1")
        assert allowed is True

    def test_reset_clears_state(self) -> None:
        bucket = _TokenBucket(max_requests=1, window_seconds=60)
        bucket.is_allowed("t1")

        allowed, _ = bucket.is_allowed("t1")
        assert allowed is False

        bucket.reset()
        allowed, _ = bucket.is_allowed("t1")
        assert allowed is True


class TestMetricsCollector:
    def test_record_and_snapshot(self) -> None:
        m = MetricsCollector()
        m.record("/api/v1/health", "tenant-a", 10.5)
        m.record("/api/v1/health", "tenant-a", 20.5)
        m.record("/api/v1/docs", "tenant-b", 5.0)

        snap = m.snapshot()
        assert snap["total_requests"] == 3
        assert snap["requests_per_endpoint"]["/api/v1/health"] == 2
        assert snap["requests_per_endpoint"]["/api/v1/docs"] == 1
        assert snap["avg_response_time_ms"] == 12.0
        assert snap["active_tenants"] == 2

    def test_empty_snapshot(self) -> None:
        m = MetricsCollector()
        snap = m.snapshot()
        assert snap["total_requests"] == 0
        assert snap["avg_response_time_ms"] == 0.0
        assert snap["active_tenants"] == 0

    def test_reset(self) -> None:
        m = MetricsCollector()
        m.record("/x", "t", 1.0)
        m.reset()
        assert m.snapshot()["total_requests"] == 0


class TestRateLimiterMiddleware:
    @pytest.fixture(autouse=True)
    def _reset_singletons(self) -> None:
        rate_limiter.reset()
        metrics.reset()

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429(self, client: AsyncClient) -> None:
        # Use a very low limit for testing
        original_max = rate_limiter.max_requests
        rate_limiter.max_requests = 2
        try:
            await client.get("/api/v1/adapters/")
            await client.get("/api/v1/adapters/")
            response = await client.get("/api/v1/adapters/")
            assert response.status_code == 429
            assert "Retry-After" in response.headers
            assert response.json()["detail"] == "Too many requests. Please retry later."
        finally:
            rate_limiter.max_requests = original_max

    @pytest.mark.asyncio
    async def test_health_exempt_from_rate_limit(self, client: AsyncClient) -> None:
        rate_limiter.max_requests = 1
        try:
            # Health should always succeed regardless of limit
            for _ in range(5):
                response = await client.get("/health")
                assert response.status_code == 200
        finally:
            rate_limiter.max_requests = 100

    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, client: AsyncClient) -> None:
        await client.get("/api/v1/adapters/")
        response = await client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        # Metrics endpoint returns health monitor data
        assert "uptime_seconds" in data or "total_requests" in data

    @pytest.mark.asyncio
    async def test_metrics_exempt_from_rate_limit(self, client: AsyncClient) -> None:
        rate_limiter.max_requests = 1
        try:
            await client.get("/api/v1/adapters/")  # uses the 1 allowed request
            # /metrics should still be reachable
            response = await client.get("/metrics")
            assert response.status_code == 200
        finally:
            rate_limiter.max_requests = 100
