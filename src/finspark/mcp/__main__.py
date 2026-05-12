"""Stdio entry point for the AdaptConfig MCP server.

Usage:
    python -m finspark.mcp          # run via module
    adaptconfig-mcp                  # run via console script
"""
from __future__ import annotations


def main() -> None:
    """Build and run the MCP server on stdio transport."""
    from finspark.mcp.server import build_server

    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
