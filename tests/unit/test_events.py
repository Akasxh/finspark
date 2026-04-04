"""Tests for the event system."""

import pytest

from finspark.core import events


class TestEventSystem:
    def setup_method(self) -> None:
        events.clear()

    @pytest.mark.asyncio
    async def test_on_registers_handler(self) -> None:
        called: list[dict] = []
        events.on("test.event", lambda data: called.append(data))
        await events.emit("test.event", {"key": "value"})
        assert len(called) == 1
        assert called[0] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self) -> None:
        await events.emit("nonexistent.event", {"data": 1})

    @pytest.mark.asyncio
    async def test_emit_calls_multiple_handlers(self) -> None:
        results: list[str] = []
        events.on("multi", lambda d: results.append("a"))
        events.on("multi", lambda d: results.append("b"))
        await events.emit("multi", {})
        assert results == ["a", "b"]

    @pytest.mark.asyncio
    async def test_emit_handler_exception_does_not_propagate(self) -> None:
        called: list[str] = []

        def failing_handler(data: dict) -> None:
            raise ValueError("boom")

        def good_handler(data: dict) -> None:
            called.append("ok")

        events.on("err.event", failing_handler)
        events.on("err.event", good_handler)
        await events.emit("err.event", {})
        assert called == ["ok"]

    @pytest.mark.asyncio
    async def test_clear_removes_all_handlers(self) -> None:
        called: list[int] = []
        events.on("clear.test", lambda d: called.append(1))
        events.clear()
        await events.emit("clear.test", {})
        assert called == []

    @pytest.mark.asyncio
    async def test_different_events_are_independent(self) -> None:
        a_calls: list[int] = []
        b_calls: list[int] = []
        events.on("event.a", lambda d: a_calls.append(1))
        events.on("event.b", lambda d: b_calls.append(1))
        await events.emit("event.a", {})
        assert len(a_calls) == 1
        assert len(b_calls) == 0

    @pytest.mark.asyncio
    async def test_handler_receives_data(self) -> None:
        received: list[dict] = []
        events.on("data.test", lambda d: received.append(d))
        await events.emit("data.test", {"config_id": "123", "status": "active"})
        assert received[0]["config_id"] == "123"
        assert received[0]["status"] == "active"

    def test_standard_event_types_defined(self) -> None:
        assert events.CONFIG_CREATED == "config.created"
        assert events.CONFIG_UPDATED == "config.updated"
        assert events.CONFIG_DEPLOYED == "config.deployed"
        assert events.CONFIG_ROLLED_BACK == "config.rolled_back"
        assert events.SIMULATION_STARTED == "simulation.started"
        assert events.SIMULATION_COMPLETED == "simulation.completed"
        assert events.DOCUMENT_PARSED == "document.parsed"
        assert events.ADAPTER_DEPRECATED == "adapter.deprecated"
