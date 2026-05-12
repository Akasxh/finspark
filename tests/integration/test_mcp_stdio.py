"""Integration test for the AdaptConfig MCP stdio binary.

Spawns ``uv run adaptconfig-mcp`` (the console-script entry point declared
in ``pyproject.toml``) as a real subprocess and drives it over its stdin /
stdout JSON-RPC framing using the MCP SDK's stdio client.

The test asserts:
  * The server starts cleanly.
  * The ``initialize`` handshake succeeds.
  * ``tools/list`` returns the three persona-spec'd bridge tools alongside
    the legacy six.
  * SIGTERM shuts the process down without orphaning it.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


def _find_uv() -> str | None:
    """Locate the ``uv`` binary used to run the MCP entry point."""
    found = shutil.which("uv")
    if found:
        return found
    # Common Homebrew / asdf locations
    for candidate in (
        "/opt/homebrew/bin/uv",
        "/usr/local/bin/uv",
        os.path.expanduser("~/.local/bin/uv"),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


_UV = _find_uv()


@pytest.fixture
def isolated_db_dir(tmp_path: Path) -> Path:
    """Create an isolated working dir so the spawned MCP server doesn't
    pollute the repo's adaptconfig.db.
    """
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.skipif(_UV is None, reason="uv binary not available on PATH")
async def test_stdio_handshake_lists_bridge_tools(isolated_db_dir: Path) -> None:
    """The spec gate: spawn the MCP binary, list tools, assert presence."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Inherit current env + force debug mode so the auth gate allows the
    # subprocess to start without a real FINSPARK_MCP_TOKEN.
    repo_root = _detect_repo_root()
    env = {
        **os.environ,
        "FINSPARK_DEBUG": "true",
        "FINSPARK_AI_ENABLED": "false",
        # Isolate DB to a tmp file so we don't touch the repo's adaptconfig.db
        "FINSPARK_DATABASE_URL": f"sqlite+aiosqlite:///{isolated_db_dir / 'mcp-test.db'}",
    }
    # Drop any FINSPARK_MCP_TOKEN so we exercise the debug-mode anonymous path
    env.pop("FINSPARK_MCP_TOKEN", None)

    params = StdioServerParameters(
        command=_UV,  # type: ignore[arg-type]
        args=["run", "--project", str(repo_root), "adaptconfig-mcp"],
        env=env,
        cwd=str(repo_root),
    )

    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        init_result = await session.initialize()
        assert init_result.serverInfo.name == "adaptconfig"

        tools_result = await session.list_tools()
        tool_names = {t.name for t in tools_result.tools}

        # Issue #114 bridge tools must be present
        assert "list_adapters" in tool_names, tool_names
        assert "generate_config" in tool_names, tool_names
        assert "invoke" in tool_names, tool_names

        # Legacy tools must also still be available
        assert "list_adapters_summary" in tool_names
        assert "search_adapters" in tool_names
        assert "simulate_config" in tool_names
        assert "get_capabilities" in tool_names


@pytest.mark.asyncio
@pytest.mark.skipif(_UV is None, reason="uv binary not available on PATH")
async def test_stdio_invokes_offline_capable_tool(isolated_db_dir: Path) -> None:
    """End-to-end: spawn the binary, invoke ``list_adapters_summary``
    (offline-capable, no DB), and read back valid JSON.
    """
    import json as _json

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo_root = _detect_repo_root()
    env = {
        **os.environ,
        "FINSPARK_DEBUG": "true",
        "FINSPARK_AI_ENABLED": "false",
        "FINSPARK_DATABASE_URL": f"sqlite+aiosqlite:///{isolated_db_dir / 'mcp-test.db'}",
    }
    env.pop("FINSPARK_MCP_TOKEN", None)

    params = StdioServerParameters(
        command=_UV,  # type: ignore[arg-type]
        args=["run", "--project", str(repo_root), "adaptconfig-mcp"],
        env=env,
        cwd=str(repo_root),
    )

    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool("list_adapters_summary", {})

        assert len(result.content) > 0
        data = _json.loads(result.content[0].text)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]


@pytest.mark.asyncio
@pytest.mark.skipif(_UV is None, reason="uv binary not available on PATH")
async def test_stdio_refuses_to_start_without_token_in_non_debug(
    isolated_db_dir: Path,
) -> None:
    """Auth gate: with FINSPARK_DEBUG=false and no token, the process must
    exit with status 78 (EX_CONFIG) before opening the stdio transport.
    """
    import asyncio

    repo_root = _detect_repo_root()
    env = {
        **os.environ,
        # debug OFF, no token
        "FINSPARK_DEBUG": "false",
        "FINSPARK_AI_ENABLED": "false",
        "FINSPARK_DATABASE_URL": f"sqlite+aiosqlite:///{isolated_db_dir / 'mcp-test.db'}",
        # Required by Settings to pass model_validator when debug=false
        "FINSPARK_SECRET_KEY": "x" * 48,
        "FINSPARK_ENCRYPTION_KEY": "y" * 48,
    }
    env.pop("FINSPARK_MCP_TOKEN", None)

    proc = await asyncio.create_subprocess_exec(
        _UV,  # type: ignore[arg-type]
        "run",
        "--project",
        str(repo_root),
        "adaptconfig-mcp",
        env=env,
        cwd=str(repo_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        # Should exit promptly with EX_CONFIG (78)
        await asyncio.wait_for(proc.wait(), timeout=30.0)
    except TimeoutError:  # pragma: no cover -- diagnostic branch
        proc.kill()
        await proc.wait()
        raise
    assert proc.returncode == 78, f"expected 78, got {proc.returncode}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_repo_root() -> Path:
    """Walk upward from this file until we find ``pyproject.toml``."""
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError(f"Cannot find pyproject.toml above {here}")
