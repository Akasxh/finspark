"""Tests for analytics service and health monitor."""

import asyncio

import pytest

from finspark.core.events import CONFIG_CREATED, clear, emit, on
from finspark.services.health_monitor import HealthMonitor


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestHealthMonitor:
    def test_monitor_creation(self) -> None:
        monitor = HealthMonitor()
        assert monitor.get_uptime() >= 0

    def test_register_and_run_check(self) -> None:
        monitor = HealthMonitor()
        monitor.register_check("test_check", lambda: {"ok": True})
        result = _run(monitor.run_all_checks())
        assert result["overall"] == "healthy"
        assert result["checks"]["test_check"]["status"] == "healthy"

    def test_unhealthy_check(self) -> None:
        monitor = HealthMonitor()
        monitor.register_check("bad_check", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        result = _run(monitor.run_all_checks())
        assert result["overall"] == "degraded"
        assert result["checks"]["bad_check"]["status"] == "unhealthy"


class TestEventSystem:
    def setup_method(self) -> None:
        clear()

    @pytest.mark.asyncio
    async def test_emit_and_handle(self) -> None:
        received: list[dict] = []
        on(CONFIG_CREATED, lambda data: received.append(data))
        await emit(CONFIG_CREATED, {"config_id": "123"})
        assert len(received) == 1
        assert received[0]["config_id"] == "123"

    @pytest.mark.asyncio
    async def test_multiple_handlers(self) -> None:
        count = [0]
        on(CONFIG_CREATED, lambda _: count.__setitem__(0, count[0] + 1))
        on(CONFIG_CREATED, lambda _: count.__setitem__(0, count[0] + 1))
        await emit(CONFIG_CREATED, {})
        assert count[0] == 2

    @pytest.mark.asyncio
    async def test_handler_error_doesnt_propagate(self) -> None:
        def bad_handler(data: dict) -> None:
            raise RuntimeError("boom")

        on(CONFIG_CREATED, bad_handler)
        await emit(CONFIG_CREATED, {})

    @pytest.mark.asyncio
    async def test_clear_handlers(self) -> None:
        received: list[dict] = []
        on(CONFIG_CREATED, lambda data: received.append(data))
        clear()
        await emit(CONFIG_CREATED, {"x": 1})
        assert len(received) == 0
