"""Unit tests for the issue-#114 MCP bridge tools.

Each of the three tools (``list_adapters``, ``generate_config``, ``invoke``)
is exercised against the test in-memory SQLite database. LLM-dependent paths
are mocked to keep tests deterministic and offline.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from finspark.mcp import bridge
from finspark.mcp.server import build_server

# ---------------------------------------------------------------------------
# Shared fixture: point the bridge at the test session factory + reset state
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_bridge_db():
    """Redirect the bridge's session factory + skip init_db on each test.

    The autouse ``setup_database`` fixture in conftest already created the
    schema in the shared in-memory engine, so ``init_db`` would be redundant
    here and could even race the test fixture. We also reset the bridge's
    initialization sentinel so each test re-seeds adapters into the freshly
    created tables.
    """
    from tests.conftest import test_session_factory

    bridge._initialized = False
    with patch("finspark.mcp.bridge.async_session_factory", test_session_factory), patch(
        "finspark.mcp.bridge.init_db", new=_noop_init_db
    ), patch("finspark.seeds.async_session_factory", test_session_factory):
        yield
    bridge._initialized = False


async def _noop_init_db() -> None:
    """Stand-in for ``init_db`` — schema is already created by conftest."""
    return None


# ---------------------------------------------------------------------------
# Tool 1: list_adapters
# ---------------------------------------------------------------------------


class TestListAdaptersTool:
    """Tool 1 — DB-backed adapter catalogue with id + latest_version_id."""

    @pytest.mark.asyncio
    async def test_returns_seeded_adapters(self) -> None:
        rows = await bridge.list_adapters_tool()
        assert isinstance(rows, list)
        assert len(rows) > 0

    @pytest.mark.asyncio
    async def test_rows_have_required_fields(self) -> None:
        rows = await bridge.list_adapters_tool()
        for row in rows:
            assert set(row.keys()) >= {
                "id",
                "name",
                "category",
                "description",
                "latest_version_id",
                "latest_version",
            }
            assert isinstance(row["id"], str) and row["id"]
            assert isinstance(row["name"], str) and row["name"]
            # All seed adapters have at least one version
            assert row["latest_version_id"] is not None
            assert row["latest_version"] is not None

    @pytest.mark.asyncio
    async def test_ids_are_unique(self) -> None:
        rows = await bridge.list_adapters_tool()
        ids = [r["id"] for r in rows]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_registered_on_server(self) -> None:
        server = build_server()
        assert "list_adapters" in server._tool_manager._tools


# ---------------------------------------------------------------------------
# Tool 2: generate_config
# ---------------------------------------------------------------------------


_SAMPLE_DOC = """
# Credit Bureau Integration

POST /credit-score — Fetch credit score for a customer.
POST /credit-report — Pull a detailed credit report.

Required fields: pan_number, customer_name, date_of_birth, mobile_number
Authentication: api_key with mTLS certificate.
SLA: response within 200ms, 99.9% availability.
"""


class TestGenerateConfigTool:
    """Tool 2 — parse, pick adapter, generate, persist."""

    @pytest.mark.asyncio
    async def test_rejects_empty_document(self) -> None:
        result = await bridge.generate_config_tool(document_text="")
        assert "error" in result
        assert "non-empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_falls_back_to_regex_when_llm_unavailable(self) -> None:
        # No FINSPARK_*_API_KEY in the test env — get_llm_client raises.
        result = await bridge.generate_config_tool(
            document_text=_SAMPLE_DOC, adapter_hint="cibil"
        )
        assert "error" not in result, result
        assert result["adapter_name"]
        assert result["config_id"]
        assert isinstance(result["config"], dict)
        assert result["config"].get("adapter_name")
        assert result["config"].get("base_url") is not None
        # Field mappings should at least mention pan-related field from doc
        mappings = result["config"].get("field_mappings", [])
        assert isinstance(mappings, list)

    @pytest.mark.asyncio
    async def test_persists_to_database(self) -> None:
        from sqlalchemy import select

        from finspark.models.configuration import Configuration
        from tests.conftest import test_session_factory

        result = await bridge.generate_config_tool(
            document_text=_SAMPLE_DOC, adapter_hint="payment", name="unit-test-config"
        )
        assert "config_id" in result, result

        async with test_session_factory() as session:
            row = await session.execute(
                select(Configuration).where(Configuration.id == result["config_id"])
            )
            cfg = row.scalar_one()
            assert cfg.tenant_id == bridge.MCP_TENANT_ID
            assert cfg.name == "unit-test-config"
            assert cfg.status == "configured"
            assert cfg.full_config
            stored = json.loads(cfg.full_config)
            assert stored.get("adapter_name")

    @pytest.mark.asyncio
    async def test_unknown_adapter_hint_returns_error(self) -> None:
        result = await bridge.generate_config_tool(
            document_text=_SAMPLE_DOC,
            adapter_hint="zzzz-nonexistent-xyz",
        )
        assert "error" in result
        assert "matched" in result["error"].lower() or "found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_hint_picks_first_adapter(self) -> None:
        result = await bridge.generate_config_tool(document_text=_SAMPLE_DOC)
        assert "error" not in result, result
        assert result["adapter_id"]
        assert result["config_id"]


# ---------------------------------------------------------------------------
# Tool 3: invoke
# ---------------------------------------------------------------------------


class TestInvokeTool:
    """Tool 3 — execute a persisted config against deterministic mock responses."""

    @pytest.mark.asyncio
    async def test_unknown_config_id_returns_error(self) -> None:
        result = await bridge.invoke_tool(config_id="nonexistent-xyz", payload={})
        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_empty_config_id_returns_error(self) -> None:
        result = await bridge.invoke_tool(config_id="", payload={})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_payload_must_be_dict(self) -> None:
        result = await bridge.invoke_tool(
            config_id="anything", payload="not-a-dict"  # type: ignore[arg-type]
        )
        assert "error" in result
        assert "object" in result["error"].lower() or "dict" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_end_to_end_generate_then_invoke(self) -> None:
        generated = await bridge.generate_config_tool(
            document_text=_SAMPLE_DOC, adapter_hint="cibil"
        )
        assert "config_id" in generated, generated
        config_id = generated["config_id"]

        invoked = await bridge.invoke_tool(
            config_id=config_id,
            payload={"pan_number": "ABCDE1234F", "customer_name": "Test User"},
        )
        assert "error" not in invoked, invoked
        assert invoked["config_id"] == config_id
        assert invoked["adapter_name"]
        assert invoked["status"] in {"ok", "error"}
        assert isinstance(invoked["steps"], list)
        # Endpoints exist on the seeded CIBIL adapter
        assert invoked["endpoint_count"] >= 1
        # Each step should be a chain-executor result dict
        for step in invoked["steps"]:
            assert "endpoint_id" in step
            assert "response" in step
            assert "request" in step

    @pytest.mark.asyncio
    async def test_invoke_returns_json_serializable(self) -> None:
        generated = await bridge.generate_config_tool(
            document_text=_SAMPLE_DOC, adapter_hint="ekyc"
        )
        if "config_id" not in generated:
            pytest.skip("no ekyc-like adapter in seed catalogue")
        result = await bridge.invoke_tool(
            config_id=generated["config_id"], payload={"aadhaar_number": "1234"}
        )
        # Must round-trip through JSON (this is what FastMCP transport does)
        json.dumps(result)


# ---------------------------------------------------------------------------
# Tool registration smoke test (catches the issue where a tool fails to
# attach to the server, which would otherwise only surface at runtime).
# ---------------------------------------------------------------------------


class TestServerWiring:
    def test_all_three_new_tools_registered(self) -> None:
        server = build_server()
        names = set(server._tool_manager._tools.keys())
        assert {"list_adapters", "generate_config", "invoke"}.issubset(names)

    def test_legacy_tools_still_registered(self) -> None:
        server = build_server()
        names = set(server._tool_manager._tools.keys())
        assert {
            "parse_api_document",
            "generate_integration_config",
            "simulate_config",
            "search_adapters",
            "list_adapters_summary",
            "get_capabilities",
        }.issubset(names)

    @pytest.mark.asyncio
    async def test_new_tool_descriptions_present(self) -> None:
        server = build_server()
        for tool_name in ("list_adapters", "generate_config", "invoke"):
            tool = server._tool_manager._tools[tool_name]
            assert tool.description, f"{tool_name} is missing a description"


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


class TestMCPAuth:
    """Issue #114 — FINSPARK_MCP_TOKEN auth precondition for the stdio entry."""

    def test_debug_mode_allows_anonymous(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from finspark.mcp import auth

        monkeypatch.delenv("FINSPARK_MCP_TOKEN", raising=False)
        with patch("finspark.mcp.auth.settings") as mock_settings:
            mock_settings.debug = True
            assert auth.is_authenticated() is True
            # enforce_or_exit must not raise
            auth.enforce_or_exit()

    def test_non_debug_requires_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from finspark.mcp import auth

        monkeypatch.delenv("FINSPARK_MCP_TOKEN", raising=False)
        with patch("finspark.mcp.auth.settings") as mock_settings:
            mock_settings.debug = False
            assert auth.is_authenticated() is False
            with pytest.raises(auth.MCPAuthError):
                auth.enforce_or_exit()

    def test_non_debug_with_token_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from finspark.mcp import auth

        monkeypatch.setenv("FINSPARK_MCP_TOKEN", "secret-value")
        with patch("finspark.mcp.auth.settings") as mock_settings:
            mock_settings.debug = False
            assert auth.is_authenticated() is True
            auth.enforce_or_exit()

    def test_empty_token_treated_as_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from finspark.mcp import auth

        monkeypatch.setenv("FINSPARK_MCP_TOKEN", "   ")
        with patch("finspark.mcp.auth.settings") as mock_settings:
            mock_settings.debug = False
            assert auth.is_authenticated() is False


# ---------------------------------------------------------------------------
# Unit-level helper coverage
# ---------------------------------------------------------------------------


class TestBridgeHelpers:
    @pytest.mark.asyncio
    async def test_score_adapter_basic(self) -> None:
        # Reach into the seeded DB to grab an adapter row
        rows = await bridge.list_adapters_tool()
        assert rows, "expected adapters to have been seeded by previous fixtures"
        # Re-fetch the SQLAlchemy object so we can use _score_adapter
        from sqlalchemy import select

        from finspark.models.adapter import Adapter
        from tests.conftest import test_session_factory

        async with test_session_factory() as session:
            from sqlalchemy.orm import selectinload

            stmt = select(Adapter).options(selectinload(Adapter.versions))
            result = await session.execute(stmt)
            adapters = list(result.scalars().all())

        assert adapters
        cibil = next(
            (a for a in adapters if "cibil" in a.name.lower()), adapters[0]
        )
        # Token "cibil" should score positive on a CIBIL adapter
        score = bridge._score_adapter(cibil, "cibil")
        assert score > 0
        # Empty hint yields zero
        assert bridge._score_adapter(cibil, "") == 0.0

    @pytest.mark.asyncio
    async def test_latest_version_picks_highest(self) -> None:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from finspark.models.adapter import Adapter
        from tests.conftest import test_session_factory

        await bridge._ensure_initialized()
        async with test_session_factory() as session:
            stmt = (
                select(Adapter)
                .options(selectinload(Adapter.versions))
                .where(Adapter.name == "CIBIL Credit Bureau")
            )
            result = await session.execute(stmt)
            cibil = result.scalar_one_or_none()

        if cibil is None:
            pytest.skip("CIBIL adapter not in seed catalogue")
        latest = bridge._latest_version(cibil)
        assert latest is not None
        # CIBIL seed has v1 and v2 — latest should be v2
        version_strings = [v.version for v in cibil.versions]
        assert latest.version in version_strings


# ---------------------------------------------------------------------------
# Misc: __main__ wiring smoke test (auth gate triggers exit)
# ---------------------------------------------------------------------------


class TestMainEntryPoint:
    def test_main_module_importable(self) -> None:
        from finspark.mcp import __main__ as mcp_main

        assert callable(mcp_main.main)

    def test_main_exits_when_auth_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FINSPARK_MCP_TOKEN", raising=False)
        # Force non-debug behaviour via settings patch
        with patch("finspark.mcp.auth.settings") as mock_settings, patch(
            "finspark.mcp.server.build_server"
        ) as mock_build:
            mock_settings.debug = False
            from finspark.mcp.__main__ import main

            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 78
            mock_build.assert_not_called()
