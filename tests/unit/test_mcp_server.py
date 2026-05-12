"""Unit tests for the AdaptConfig MCP server.

Tests verify tool registration, input/output schemas, and that each tool
produces well-formed results when underlying services are mocked.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finspark.mcp.server import build_server


@pytest.fixture
def mcp_server():
    """Build a fresh MCP server instance."""
    return build_server()


class TestServerConstruction:
    """Verify the server builds correctly with all tools registered."""

    def test_build_server_returns_fastmcp(self, mcp_server):
        from mcp.server.fastmcp import FastMCP

        assert isinstance(mcp_server, FastMCP)

    def test_server_has_correct_name(self, mcp_server):
        assert mcp_server.name == "adaptconfig"

    def test_all_tools_registered(self, mcp_server):
        tool_names = set(mcp_server._tool_manager._tools.keys())
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
        assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


class TestListAdaptersSummary:
    """Test the legacy seed-JSON `list_adapters_summary` tool."""

    def test_returns_non_empty_list(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["list_adapters_summary"].fn
        result = json.loads(tool_fn())
        assert isinstance(result, list)
        assert len(result) > 0

    def test_adapter_has_required_fields(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["list_adapters_summary"].fn
        result = json.loads(tool_fn())
        for adapter in result:
            assert "name" in adapter
            assert "category" in adapter
            assert "auth_types" in adapter
            assert "version_count" in adapter
            assert isinstance(adapter["version_count"], int)
            assert adapter["version_count"] > 0


class TestSearchAdapters:
    """Test the search_adapters tool."""

    def test_search_by_category(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["search_adapters"].fn
        result = json.loads(tool_fn("payment"))
        assert isinstance(result, list)
        assert len(result) > 0
        for r in result:
            assert r["score"] > 0

    def test_search_by_name(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["search_adapters"].fn
        result = json.loads(tool_fn("CIBIL"))
        assert isinstance(result, list)
        assert len(result) > 0
        assert any("CIBIL" in r["name"] for r in result)

    def test_search_no_results(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["search_adapters"].fn
        result = json.loads(tool_fn("xyznonexistent12345"))
        assert isinstance(result, list)
        assert len(result) == 0

    def test_results_sorted_by_score(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["search_adapters"].fn
        result = json.loads(tool_fn("credit bureau"))
        if len(result) > 1:
            scores = [r["score"] for r in result]
            assert scores == sorted(scores, reverse=True)


class TestGetCapabilities:
    """Test the get_capabilities tool."""

    def test_returns_metadata(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["get_capabilities"].fn
        result = tool_fn()
        assert result["server"] == "adaptconfig"
        assert result["version"] == "0.1.0"
        assert "tools" in result
        assert isinstance(result["tools"], list)
        # 6 legacy tools + 3 new bridge tools (issue #114)
        assert len(result["tools"]) == 9

    def test_adapter_count_matches_catalog(self, mcp_server):
        tool_fn_caps = mcp_server._tool_manager._tools["get_capabilities"].fn
        tool_fn_list = mcp_server._tool_manager._tools["list_adapters_summary"].fn
        caps = tool_fn_caps()
        adapters = json.loads(tool_fn_list())
        assert caps["adapter_count"] == len(adapters)

    def test_offline_capable_tools_listed(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["get_capabilities"].fn
        result = tool_fn()
        assert "simulate_config" in result["offline_capable"]
        assert "search_adapters" in result["offline_capable"]
        assert "list_adapters_summary" in result["offline_capable"]


class TestSimulateConfig:
    """Test the simulate_config tool."""

    def test_basic_simulation(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["simulate_config"].fn
        config: dict[str, Any] = {
            "adapter_name": "test",
            "version": "v1",
            "base_url": "https://api.test.com",
            "auth": {"type": "api_key"},
            "endpoints": [
                {"path": "/test", "method": "POST", "enabled": True}
            ],
            "field_mappings": [
                {
                    "source_field": "pan_number",
                    "target_field": "pan",
                    "confidence": 0.95,
                }
            ],
        }
        result = json.loads(tool_fn(config, "full"))
        assert isinstance(result, list)
        assert len(result) > 0
        for step in result:
            assert "step_name" in step
            assert "status" in step
            assert step["status"] in {"passed", "failed", "skipped", "error"}

    def test_smoke_test_type(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["simulate_config"].fn
        config: dict[str, Any] = {
            "adapter_name": "test",
            "version": "v1",
            "base_url": "https://api.test.com",
            "auth": {"type": "api_key"},
            "endpoints": [],
            "field_mappings": [],
        }
        full_result = json.loads(tool_fn(config, "full"))
        smoke_result = json.loads(tool_fn(config, "smoke"))
        # Smoke should have fewer steps than full
        assert len(smoke_result) <= len(full_result)


class TestParseApiDocument:
    """Test the parse_api_document tool (with mocked LLM)."""

    @pytest.mark.asyncio
    async def test_fallback_to_regex(self, mcp_server):
        """When LLM client raises, falls back to regex parser."""
        tool_fn = mcp_server._tool_manager._tools["parse_api_document"].fn

        text = """
        # Credit Bureau API Specification

        POST /api/v1/credit-score
        POST /api/v1/credit-report

        Fields: pan_number, customer_name, date_of_birth

        Authentication: api_key, bearer token
        """
        # Mock get_llm_client to raise so regex fallback kicks in
        with patch(
            "finspark.services.parsing.document_parser.GeminiClient",
            side_effect=ValueError("No API key"),
        ):
            result = await tool_fn(text, "credit_api.yaml")

        assert isinstance(result, dict)
        assert "doc_type" in result
        assert "endpoints" in result
        assert "fields" in result

    @pytest.mark.asyncio
    async def test_returns_json_serializable(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["parse_api_document"].fn

        with patch(
            "finspark.services.parsing.document_parser.GeminiClient",
            side_effect=ValueError("No API key"),
        ):
            result = await tool_fn("Simple test text with PAN and Aadhaar", "test.txt")

        # Must be JSON serializable
        json.dumps(result)


class TestGenerateIntegrationConfig:
    """Test the generate_integration_config tool."""

    @pytest.mark.asyncio
    async def test_unknown_adapter_returns_error(self, mcp_server):
        tool_fn = mcp_server._tool_manager._tools["generate_integration_config"].fn
        result = await tool_fn("nonexistent-adapter-xyz", "some doc text")
        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_adapter_lookup_by_partial_name(self, mcp_server):
        """Adapter lookup matches partial names from seed data."""
        tool_fn = mcp_server._tool_manager._tools["generate_integration_config"].fn
        # "CIBIL" should match "CIBIL Credit Bureau" from seeds
        with patch(
            "finspark.services.llm.client.get_llm_client",
            side_effect=ValueError("No key"),
        ):
            # Will fail at LLM stage but should not fail at adapter lookup
            result = await tool_fn("CIBIL", "Test doc with pan_number field")
        # Should either have config keys or error from LLM, not adapter-not-found
        if "error" in result:
            assert "not found" not in result["error"]
