"""
Demonstrates async test patterns with pytest-asyncio.

Covers:
- Basic async test function
- Async fixture chaining
- Concurrent coroutine execution inside a test
- Timeout guard for hung coroutines
- Async generator fixture
- Testing async context managers
- Async iteration
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1. Basic async test
# ---------------------------------------------------------------------------


async def test_simple_async() -> None:
    """pytest-asyncio turns this into a coroutine test automatically."""
    await asyncio.sleep(0)  # yield once
    assert True


# ---------------------------------------------------------------------------
# 2. Async fixture → test chain
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def async_resource() -> AsyncGenerator[dict[str, Any], None]:
    """Async fixture that yields a resource and cleans up after the test."""
    resource: dict[str, Any] = {"ready": True, "calls": 0}
    yield resource
    resource["ready"] = False  # teardown


async def test_async_fixture_chain(async_resource: dict[str, Any]) -> None:
    assert async_resource["ready"] is True
    async_resource["calls"] += 1
    assert async_resource["calls"] == 1


# ---------------------------------------------------------------------------
# 3. Concurrent tasks inside one test
# ---------------------------------------------------------------------------


async def test_concurrent_tasks_complete() -> None:
    results: list[int] = []

    async def _worker(n: int) -> None:
        await asyncio.sleep(0)
        results.append(n)

    await asyncio.gather(*[_worker(i) for i in range(10)])
    assert sorted(results) == list(range(10))


# ---------------------------------------------------------------------------
# 4. Timeout guard
# ---------------------------------------------------------------------------


@pytest.mark.timeout(2)
async def test_coroutine_completes_within_timeout() -> None:
    """
    @pytest.mark.timeout(2) kills the test after 2 seconds.
    The coroutine below should finish well under that.
    """
    await asyncio.sleep(0.01)
    assert True


# ---------------------------------------------------------------------------
# 5. AsyncMock usage
# ---------------------------------------------------------------------------


async def test_async_mock_called_correctly() -> None:
    mock_service = AsyncMock()
    mock_service.process.return_value = {"status": "ok"}

    result = await mock_service.process({"input": "data"})
    assert result["status"] == "ok"
    mock_service.process.assert_awaited_once_with({"input": "data"})


async def test_async_mock_side_effects() -> None:
    mock_fn = AsyncMock(side_effect=[ValueError("first"), "second", "third"])

    with pytest.raises(ValueError, match="first"):
        await mock_fn()

    assert await mock_fn() == "second"
    assert await mock_fn() == "third"


# ---------------------------------------------------------------------------
# 6. Async context manager
# ---------------------------------------------------------------------------


class _AsyncCtxMgr:
    def __init__(self) -> None:
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> "_AsyncCtxMgr":
        self.entered = True
        return self

    async def __aexit__(self, *_: object) -> None:
        self.exited = True


async def test_async_context_manager() -> None:
    mgr = _AsyncCtxMgr()
    async with mgr:
        assert mgr.entered is True
        assert mgr.exited is False
    assert mgr.exited is True


# ---------------------------------------------------------------------------
# 7. Async iteration
# ---------------------------------------------------------------------------


async def _async_gen() -> AsyncGenerator[int, None]:
    for i in range(5):
        await asyncio.sleep(0)
        yield i


async def test_async_iteration() -> None:
    collected = [i async for i in _async_gen()]
    assert collected == [0, 1, 2, 3, 4]


# ---------------------------------------------------------------------------
# 8. Task cancellation
# ---------------------------------------------------------------------------


async def test_task_cancellation_is_handled() -> None:
    cancelled = False

    async def _long_running() -> None:
        nonlocal cancelled
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            cancelled = True
            raise

    task = asyncio.create_task(_long_running())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled is True


# ---------------------------------------------------------------------------
# 9. gather with error handling
# ---------------------------------------------------------------------------


async def test_gather_returns_partial_results_on_error() -> None:
    async def _ok() -> str:
        return "ok"

    async def _fail() -> str:
        raise ValueError("boom")

    results = await asyncio.gather(_ok(), _fail(), _ok(), return_exceptions=True)
    assert results[0] == "ok"
    assert isinstance(results[1], ValueError)
    assert results[2] == "ok"


# ---------------------------------------------------------------------------
# 10. Session-scoped async fixture (shared across tests in this module)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def module_cache() -> AsyncGenerator[dict[str, Any], None]:
    """
    Module-scoped: created once for all tests in this file.
    Useful for expensive setup like loading ML models or seed data.
    """
    cache: dict[str, Any] = {"initialised": True, "hit_count": 0}
    yield cache
    # teardown — runs once after all tests in this module complete


async def test_module_cache_is_shared_1(module_cache: dict[str, Any]) -> None:
    module_cache["hit_count"] += 1
    assert module_cache["initialised"] is True


async def test_module_cache_is_shared_2(module_cache: dict[str, Any]) -> None:
    # hit_count carries over from test_1 because fixture is module-scoped
    assert module_cache["hit_count"] >= 1
