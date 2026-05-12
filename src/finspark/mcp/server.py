"""AdaptConfig MCP server exposing platform capabilities as MCP tools.

The server is a SEPARATE process from the FastAPI app. Services are
lazy-imported to avoid pulling in the full FastAPI dependency graph.
When no database is available, adapter tools fall back to the seeded
JSON catalog.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

_SEED_FILE = Path(__file__).resolve().parent.parent / "seeds" / "adapters.json"


def _load_seed_adapters() -> list[dict[str, Any]]:
    """Load the adapter catalog from the bundled JSON seed file."""
    with open(_SEED_FILE) as f:
        return json.load(f)


def build_server() -> FastMCP:
    """Construct and return the AdaptConfig MCP server with all tools registered."""

    mcp = FastMCP(
        name="adaptconfig",
        instructions=(
            "AdaptConfig MCP server. Exposes tools for parsing API documents, "
            "generating integration configs, running simulations, and browsing "
            "the adapter catalog for Indian fintech lending platforms."
        ),
    )

    # ------------------------------------------------------------------
    # Tool: parse_api_document
    # ------------------------------------------------------------------
    @mcp.tool(
        name="parse_api_document",
        description=(
            "Parse an API document (BRD, SOW, OpenAPI spec, or free text) and "
            "extract structured integration requirements: endpoints, fields, "
            "auth, SLAs, and security constraints."
        ),
    )
    async def parse_api_document(
        text: str,
        filename: str = "spec.yaml",
    ) -> dict[str, Any]:
        from finspark.services.llm.client import get_llm_client
        from finspark.services.parsing.document_parser import DocumentParser

        parser = DocumentParser()
        try:
            client = get_llm_client()
            result = await parser.parse_with_llm(text, filename, client)
        except Exception:
            logger.info("LLM unavailable, falling back to regex parser")
            result = parser.parse_text(text)
        return result.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Tool: generate_integration_config
    # ------------------------------------------------------------------
    @mcp.tool(
        name="generate_integration_config",
        description=(
            "Generate a complete integration configuration for a given adapter "
            "using a parsed API document. Produces endpoint configs, field "
            "mappings, auth setup, retry logic, and chaining rules."
        ),
    )
    async def generate_integration_config(
        adapter_id: str,
        document_text: str,
        name: str = "Generated config",
    ) -> dict[str, Any]:
        from finspark.services.llm.client import get_llm_client
        from finspark.services.llm.config_generator import generate_config_llm
        from finspark.services.parsing.document_parser import DocumentParser

        # Look up adapter from seed data (no DB needed)
        adapters = _load_seed_adapters()
        adapter_info: dict[str, Any] | None = None
        for adapter in adapters:
            if adapter.get("name", "").lower().replace(" ", "-") == adapter_id.lower():
                adapter_info = adapter
                break
        # Also try partial match on name
        if adapter_info is None:
            for adapter in adapters:
                if adapter_id.lower() in adapter.get("name", "").lower():
                    adapter_info = adapter
                    break
        if adapter_info is None:
            return {"error": f"Adapter '{adapter_id}' not found in catalog"}

        # Parse the document
        parser = DocumentParser()
        try:
            client = get_llm_client()
            parsed = await parser.parse_with_llm(document_text, "document.txt", client)
        except Exception:
            parsed = parser.parse_text(document_text)

        document_content = parsed.model_dump(mode="json")

        # Generate config via LLM
        try:
            client = get_llm_client()
            config = await generate_config_llm(
                adapter_info=adapter_info,
                document_content=document_content,
                client=client,
            )
        except Exception as exc:
            return {"error": f"Config generation failed: {exc}", "name": name}

        config["name"] = name
        return config

    # ------------------------------------------------------------------
    # Tool: simulate_config
    # ------------------------------------------------------------------
    @mcp.tool(
        name="simulate_config",
        description=(
            "Run a simulation against an integration configuration to validate "
            "its structure, field mappings, auth, endpoints, error handling, "
            "and retry logic. Returns step-by-step results."
        ),
    )
    def simulate_config(
        config: dict[str, Any],
        test_type: str = "full",
    ) -> str:
        from finspark.services.simulation.simulator import IntegrationSimulator

        simulator = IntegrationSimulator()
        steps = simulator.run_simulation(config, test_type=test_type)
        return json.dumps([step.model_dump(mode="json") for step in steps], indent=2)

    # ------------------------------------------------------------------
    # Tool: search_adapters
    # ------------------------------------------------------------------
    @mcp.tool(
        name="search_adapters",
        description=(
            "Search the adapter catalog by keyword. Matches against adapter "
            "names, categories, descriptions, and auth types. Works offline "
            "from the bundled seed data (no database required)."
        ),
    )
    def search_adapters(query: str) -> str:
        import re

        adapters = _load_seed_adapters()
        query_lower = query.lower()
        tokens = re.findall(r"[a-z0-9_]+", query_lower)
        results: list[dict[str, Any]] = []

        for adapter in adapters:
            name_lower = adapter.get("name", "").lower()
            desc_lower = adapter.get("description", "").lower()
            cat_lower = adapter.get("category", "").lower()
            score = 0.0

            for token in tokens:
                if token in name_lower:
                    score += 3.0
                if token in desc_lower:
                    score += 1.0
                if token in cat_lower:
                    score += 5.0

            if score > 0:
                versions = adapter.get("versions", [])
                auth_types = list({v.get("auth_type", "") for v in versions})
                results.append({
                    "name": adapter.get("name"),
                    "category": adapter.get("category"),
                    "description": adapter.get("description"),
                    "auth_types": auth_types,
                    "score": score,
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return json.dumps(results, indent=2)

    # ------------------------------------------------------------------
    # Tool: list_adapters_summary (legacy seed-JSON view; the canonical
    # `list_adapters` below returns DB-backed rows including stable ids).
    # ------------------------------------------------------------------
    @mcp.tool(
        name="list_adapters_summary",
        description=(
            "Return a seed-JSON-backed summary of the adapter catalogue with "
            "name, category, auth types, and version count. Offline-capable. "
            "For stable ids and DB-synchronised data, prefer `list_adapters`."
        ),
    )
    def list_adapters_summary() -> str:
        adapters = _load_seed_adapters()
        result: list[dict[str, Any]] = []

        for adapter in adapters:
            versions = adapter.get("versions", [])
            auth_types = list({v.get("auth_type", "") for v in versions})
            result.append({
                "name": adapter.get("name"),
                "category": adapter.get("category"),
                "description": adapter.get("description"),
                "auth_types": auth_types,
                "version_count": len(versions),
            })

        return json.dumps(result, indent=2)

    # ------------------------------------------------------------------
    # Tool: get_capabilities
    # ------------------------------------------------------------------
    @mcp.tool(
        name="get_capabilities",
        description="Returns metadata about the AdaptConfig MCP server and its tools.",
    )
    def get_capabilities() -> dict[str, Any]:
        adapters = _load_seed_adapters()
        categories = sorted({a.get("category", "") for a in adapters})
        return {
            "server": "adaptconfig",
            "version": "0.1.0",
            "description": (
                "AI-powered integration configuration platform for Indian "
                "fintech lending. Parse API docs, generate configs, run "
                "simulations, and browse the adapter catalog."
            ),
            "tools": [
                "parse_api_document",
                "generate_integration_config",
                "simulate_config",
                "search_adapters",
                "list_adapters",
                "list_adapters_summary",
                "get_capabilities",
                "generate_config",
                "invoke",
            ],
            "adapter_count": len(adapters),
            "adapter_categories": categories,
            "requires_llm": ["parse_api_document", "generate_integration_config"],
            "offline_capable": [
                "simulate_config",
                "search_adapters",
                "list_adapters_summary",
                "get_capabilities",
            ],
        }

    # ------------------------------------------------------------------
    # Issue #114 bridge tools — persona-spec'd contract
    # ------------------------------------------------------------------
    # These three tools form the runtime API proxy / integration middleware
    # surface. They reuse DocumentParser, ConfigGenerator, and the chain
    # executor + mock responses directly via finspark.mcp.bridge — no HTTP
    # round-trips back to the FastAPI server.
    from finspark.mcp import bridge

    @mcp.tool(
        name="list_adapters",
        description=(
            "Return the adapter catalogue from the database with one row per "
            "adapter: id, name, category, description, latest_version_id, and "
            "latest_version. Use this output's `id` and `latest_version_id` "
            "as stable references for downstream tools."
        ),
    )
    async def list_adapters() -> list[dict[str, Any]]:
        return await bridge.list_adapters_tool()

    @mcp.tool(
        name="generate_config",
        description=(
            "Parse a free-text API document, pick the best adapter (using an "
            "optional hint like 'cibil' or 'razorpay'), generate a runnable "
            "integration config via the rule-based ConfigGenerator, and "
            "persist it. Returns a `config_id` that can be passed to `invoke`."
        ),
    )
    async def generate_config(
        document_text: str,
        adapter_hint: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return await bridge.generate_config_tool(
            document_text=document_text,
            adapter_hint=adapter_hint,
            name=name,
        )

    @mcp.tool(
        name="invoke",
        description=(
            "Execute a previously generated configuration against deterministic "
            "mock responses via the chain executor. Pass the `config_id` returned "
            "by `generate_config` and an optional payload that will be merged "
            "into each endpoint's request body. Returns step-by-step chain "
            "results and the final response."
        ),
    )
    async def invoke(
        config_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await bridge.invoke_tool(config_id=config_id, payload=payload)

    return mcp
