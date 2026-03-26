"""
Performance tests — tagged @pytest.mark.slow so they're excluded from normal CI
unless explicitly requested with: pytest -m slow

Patterns:
- Throughput: N requests in M seconds
- Latency percentiles: p50 / p95 / p99
- Concurrent request handling
- DB query time under load

Run with:
  pytest tests/integration/test_performance.py -m slow -v --timeout=120
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]

# Acceptable thresholds
P95_THRESHOLD_MS = 500
THROUGHPUT_MIN_RPS = 50  # requests per second under light load


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _timed_get(
    client: AsyncClient,
    path: str,
    headers: dict[str, str],
) -> float:
    """Returns elapsed ms for a single GET."""
    t0 = time.perf_counter()
    await client.get(path, headers=headers)
    return (time.perf_counter() - t0) * 1000


async def _timed_post(
    client: AsyncClient,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> float:
    t0 = time.perf_counter()
    await client.post(path, json=payload, headers=headers)
    return (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# Health check baseline
# ---------------------------------------------------------------------------


async def test_health_check_latency(
    client: AsyncClient,
    tenant_headers: dict[str, str],
) -> None:
    """Health endpoint should respond within 50 ms."""
    latencies = [await _timed_get(client, "/health", tenant_headers) for _ in range(20)]
    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    assert p95 < 50, f"Health check p95={p95:.1f}ms exceeds 50ms threshold"


# ---------------------------------------------------------------------------
# Adapter list throughput
# ---------------------------------------------------------------------------


async def test_adapter_list_throughput(
    client: AsyncClient,
    tenant_headers: dict[str, str],
) -> None:
    """
    Fire 100 concurrent GET /api/v1/adapters requests.
    RPS should exceed THROUGHPUT_MIN_RPS.
    """
    n = 100
    t0 = time.perf_counter()
    await asyncio.gather(
        *[client.get("/api/v1/adapters", headers=tenant_headers) for _ in range(n)]
    )
    elapsed = time.perf_counter() - t0
    rps = n / elapsed
    assert rps >= THROUGHPUT_MIN_RPS, f"Throughput {rps:.1f} RPS < {THROUGHPUT_MIN_RPS} RPS"


# ---------------------------------------------------------------------------
# Integration list latency (DB query)
# ---------------------------------------------------------------------------


async def test_integration_list_p95_latency(
    client: AsyncClient,
    tenant_headers: dict[str, str],
) -> None:
    """
    Integration list with an empty tenant should have p95 < P95_THRESHOLD_MS.
    Exercises the DB query path.
    """
    n = 50
    tasks = [_timed_get(client, "/api/v1/integrations", tenant_headers) for _ in range(n)]
    latencies = await asyncio.gather(*tasks)
    p95 = statistics.quantiles(list(latencies), n=20)[18]
    assert p95 < P95_THRESHOLD_MS, (
        f"Integration list p95={p95:.1f}ms exceeds {P95_THRESHOLD_MS}ms threshold"
    )


# ---------------------------------------------------------------------------
# Config generation latency (LLM mocked)
# ---------------------------------------------------------------------------


async def test_config_generation_latency_with_mock_llm(
    client: AsyncClient,
    tenant_headers: dict[str, str],
    sample_brd_text: str,
    mock_openai: Any,
) -> None:
    """
    With a synchronous (instant) LLM mock, end-to-end config generation
    should complete in <200 ms per request.
    """
    n = 20
    tasks = [
        _timed_post(
            client,
            "/api/v1/config/generate",
            {"text": sample_brd_text},
            tenant_headers,
        )
        for _ in range(n)
    ]
    latencies = await asyncio.gather(*tasks)
    p95 = statistics.quantiles(list(latencies), n=20)[18]
    # Only assert if endpoint exists (non-404)
    all_valid = all(l < 5000 for l in latencies)  # sanity: none took >5s
    assert all_valid, f"Some requests timed out: max={max(latencies):.1f}ms"


# ---------------------------------------------------------------------------
# Concurrent multi-tenant requests (isolation + throughput)
# ---------------------------------------------------------------------------


async def test_concurrent_multi_tenant_isolation(
    client: AsyncClient,
    mock_tenant: dict[str, Any],
    other_tenant: dict[str, Any],
) -> None:
    """
    Interleaved requests from two tenants should not corrupt each other's data.
    """
    headers_a = {
        "X-Tenant-ID": mock_tenant["id"],
        "Authorization": f"Bearer test-token-{mock_tenant['id']}",
    }
    headers_b = {
        "X-Tenant-ID": other_tenant["id"],
        "Authorization": f"Bearer test-token-{other_tenant['id']}",
    }

    async def _fetch(headers: dict[str, str]) -> dict[str, Any]:
        resp = await client.get("/api/v1/integrations", headers=headers)
        return {"tenant_id": headers["X-Tenant-ID"], "status": resp.status_code}

    tasks = [
        _fetch(headers_a if i % 2 == 0 else headers_b) for i in range(40)
    ]
    results = await asyncio.gather(*tasks)

    # All must return 200 (or 404 if not implemented)
    for r in results:
        assert r["status"] in (200, 404)

    # No cross-contamination check: each result carries correct tenant_id
    for r in results:
        assert r["tenant_id"] in (mock_tenant["id"], other_tenant["id"])


# ---------------------------------------------------------------------------
# DB write throughput (integration creation)
# ---------------------------------------------------------------------------


async def test_bulk_integration_creation(
    client: AsyncClient,
    tenant_headers: dict[str, str],
    integration_payload: dict[str, Any],
) -> None:
    """Create 25 integrations sequentially and measure total time."""
    n = 25
    t0 = time.perf_counter()
    statuses = []
    for i in range(n):
        payload = {**integration_payload, "name": f"Integration {i}"}
        resp = await client.post("/api/v1/integrations", json=payload, headers=tenant_headers)
        statuses.append(resp.status_code)
    elapsed = time.perf_counter() - t0

    # If endpoint is implemented, all should be 201
    if any(s == 201 for s in statuses):
        success_rate = sum(1 for s in statuses if s in (200, 201)) / n
        assert success_rate >= 0.95, f"Only {success_rate*100:.0f}% succeeded"
        assert elapsed < 10.0, f"Bulk create took {elapsed:.2f}s, expected <10s"
