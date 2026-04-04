"""Tests for configurable rate limiter (Issue #65)."""

import pytest

from finspark.core.config import Settings
from finspark.core.rate_limiter import _TokenBucket


class TestRateLimiterConfig:
    def test_default_rate_limit_settings(self) -> None:
        s = Settings(debug=True)
        assert s.rate_limit_max_requests == 100
        assert s.rate_limit_window_seconds == 60

    def test_custom_rate_limit_settings(self) -> None:
        s = Settings(debug=True, rate_limit_max_requests=50, rate_limit_window_seconds=30)
        assert s.rate_limit_max_requests == 50
        assert s.rate_limit_window_seconds == 30

    @pytest.mark.asyncio
    async def test_token_bucket_respects_custom_max_requests(self) -> None:
        bucket = _TokenBucket(max_requests=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = await bucket.is_allowed("t1")
            assert allowed is True

        allowed, _ = await bucket.is_allowed("t1")
        assert allowed is False

    @pytest.mark.asyncio
    async def test_token_bucket_respects_custom_window(self) -> None:
        import time

        bucket = _TokenBucket(max_requests=1, window_seconds=1)
        await bucket.is_allowed("t1")

        allowed, _ = await bucket.is_allowed("t1")
        assert allowed is False

        # Simulate expiry by pushing timestamps back
        async with bucket._lock:
            bucket._requests["t1"] = [time.monotonic() - 2]

        allowed, _ = await bucket.is_allowed("t1")
        assert allowed is True
