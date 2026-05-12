"""Stdio entry point for the AdaptConfig MCP server.

Usage:
    python -m finspark.mcp          # run via module
    adaptconfig-mcp                  # run via console script

The console script enforces ``FINSPARK_MCP_TOKEN`` when ``FINSPARK_DEBUG=false``.
In debug mode anonymous start-up is permitted (a warning is logged).
"""
from __future__ import annotations

import logging
import sys


def main() -> None:
    """Build and run the MCP server on stdio transport.

    Auth precondition is enforced before the transport is opened so that
    misconfigured deployments fail fast rather than serving without a token.
    """
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    from finspark.mcp.auth import MCPAuthError, enforce_or_exit
    from finspark.mcp.server import build_server

    try:
        enforce_or_exit()
    except MCPAuthError:
        sys.exit(78)  # EX_CONFIG

    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
