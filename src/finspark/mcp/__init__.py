"""AdaptConfig MCP (Model Context Protocol) server package.

Issue #114 — runtime API proxy / integration middleware over stdio. The
server is a *separate process* from the FastAPI app: tools reuse the same
service classes (DocumentParser, ConfigGenerator, IntegrationSimulator,
chain executor) directly and share the same SQLite/Postgres database, but
no HTTP round-trip is involved.
"""
from finspark.mcp.server import build_server

__all__ = ["build_server"]
