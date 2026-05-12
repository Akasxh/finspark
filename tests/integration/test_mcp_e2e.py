"""End-to-end integration tests for the AdaptConfig MCP server.

Uses the MCP SDK's in-memory transport to spin up the server in-process
and invoke tools via a real MCP ClientSession.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from finspark.mcp.server import build_server


def _parse_tool_result(result) -> Any:
    """Parse MCP tool result content into a Python object.

    Tools return JSON strings which MCP wraps in a single TextContent item.
    """
    assert len(result.content) > 0
    return json.loads(result.content[0].text)


async def _run_with_client(coro_fn):
    """Helper: create an in-memory MCP client, run a coroutine with it, close."""
    from mcp.shared.memory import create_connected_server_and_client_session

    server = build_server()
    async with create_connected_server_and_client_session(server) as client_session:
        await client_session.initialize()
        return await coro_fn(client_session)


class TestToolDiscovery:
    """Verify the client can discover all tools."""

    @pytest.mark.asyncio
    async def test_list_tools(self):
        async def _test(client):
            tools_result = await client.list_tools()
            tool_names = {t.name for t in tools_result.tools}
            expected = {
                "parse_api_document",
                "generate_integration_config",
                "simulate_config",
                "search_adapters",
                "list_adapters",
                "list_adapters_summary",
                "get_capabilities",
                "generate_config",
                "invoke",
            }
            assert expected.issubset(tool_names)

        await _run_with_client(_test)

    @pytest.mark.asyncio
    async def test_tools_have_descriptions(self):
        async def _test(client):
            tools_result = await client.list_tools()
            for tool in tools_result.tools:
                assert tool.description, f"Tool {tool.name} has no description"

        await _run_with_client(_test)

    @pytest.mark.asyncio
    async def test_tools_have_input_schemas(self):
        async def _test(client):
            tools_result = await client.list_tools()
            for tool in tools_result.tools:
                assert tool.inputSchema is not None, f"Tool {tool.name} has no input schema"

        await _run_with_client(_test)


class TestGetCapabilitiesE2E:
    """Invoke get_capabilities via MCP protocol."""

    @pytest.mark.asyncio
    async def test_invoke(self):
        async def _test(client):
            result = await client.call_tool("get_capabilities", {})
            data = _parse_tool_result(result)
            assert data["server"] == "adaptconfig"
            assert isinstance(data["tools"], list)

        await _run_with_client(_test)


class TestListAdaptersSummaryE2E:
    """Invoke the legacy seed-JSON `list_adapters_summary` via MCP protocol."""

    @pytest.mark.asyncio
    async def test_invoke(self):
        async def _test(client):
            result = await client.call_tool("list_adapters_summary", {})
            data = _parse_tool_result(result)
            assert isinstance(data, list)
            assert len(data) > 0
            assert "name" in data[0]
            assert "category" in data[0]

        await _run_with_client(_test)


class TestSearchAdaptersE2E:
    """Invoke search_adapters via MCP protocol."""

    @pytest.mark.asyncio
    async def test_search_payment(self):
        async def _test(client):
            result = await client.call_tool("search_adapters", {"query": "payment"})
            data = _parse_tool_result(result)
            assert isinstance(data, list)
            assert len(data) > 0

        await _run_with_client(_test)

    @pytest.mark.asyncio
    async def test_search_no_match(self):
        async def _test(client):
            result = await client.call_tool(
                "search_adapters", {"query": "xyznonexistent12345"}
            )
            data = _parse_tool_result(result)
            assert isinstance(data, list)
            assert len(data) == 0

        await _run_with_client(_test)


class TestSimulateConfigE2E:
    """Invoke simulate_config via MCP protocol."""

    @pytest.mark.asyncio
    async def test_invoke(self):
        async def _test(client):
            config: dict[str, Any] = {
                "adapter_name": "test-adapter",
                "version": "v1",
                "base_url": "https://api.test.com/v1",
                "auth": {"type": "api_key"},
                "endpoints": [
                    {"path": "/credit-score", "method": "POST", "enabled": True}
                ],
                "field_mappings": [
                    {
                        "source_field": "pan_number",
                        "target_field": "pan",
                        "confidence": 0.95,
                    }
                ],
            }
            result = await client.call_tool(
                "simulate_config",
                {"config": config, "test_type": "smoke"},
            )
            data = _parse_tool_result(result)
            assert isinstance(data, list)
            assert len(data) > 0
            assert "step_name" in data[0]
            assert data[0]["status"] in {"passed", "failed", "skipped", "error"}

        await _run_with_client(_test)


class TestParseApiDocumentE2E:
    """Invoke parse_api_document via MCP protocol (LLM mocked)."""

    @pytest.mark.asyncio
    async def test_invoke_with_regex_fallback(self):
        async def _test(client):
            text = """
            POST /api/v1/credit-score
            POST /api/v1/credit-report

            Required fields: pan_number, customer_name, date_of_birth
            Authentication: api_key
            """
            result = await client.call_tool(
                "parse_api_document",
                {"text": text, "filename": "credit_api.yaml"},
            )
            data = _parse_tool_result(result)
            assert "doc_type" in data
            assert "endpoints" in data
            assert "fields" in data

        await _run_with_client(_test)


class TestGenerateIntegrationConfigE2E:
    """Invoke generate_integration_config via MCP protocol."""

    @pytest.mark.asyncio
    async def test_unknown_adapter(self):
        async def _test(client):
            result = await client.call_tool(
                "generate_integration_config",
                {
                    "adapter_id": "nonexistent-xyz",
                    "document_text": "some doc",
                },
            )
            data = _parse_tool_result(result)
            assert "error" in data
            assert "not found" in data["error"]

        await _run_with_client(_test)
