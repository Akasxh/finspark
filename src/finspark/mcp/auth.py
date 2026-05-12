"""Startup auth check for the AdaptConfig MCP server.

Reads ``FINSPARK_MCP_TOKEN`` from the process environment. In non-debug mode
the server refuses to start when the token is absent or empty. In debug mode
anonymous start-up is permitted (a warning is logged).

The token gates *whether the server process starts*; stdio MCP itself is a
local-trust transport. A future networked transport (HTTP/SSE) would need
per-request validation in addition to this start-up gate.
"""
from __future__ import annotations

import logging
import os
import sys

from finspark.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_ENV_VAR = "FINSPARK_MCP_TOKEN"


class MCPAuthError(RuntimeError):
    """Raised when the MCP server cannot satisfy its auth precondition."""


def get_token() -> str:
    """Return the configured MCP token, or an empty string when unset."""
    return os.environ.get(_TOKEN_ENV_VAR, "").strip()


def is_authenticated() -> bool:
    """Return True when the server is allowed to serve requests.

    - Non-debug: requires a non-empty ``FINSPARK_MCP_TOKEN``.
    - Debug: always returns True (anonymous start-up permitted, with a warning).
    """
    token = get_token()
    if settings.debug:
        if not token:
            logger.warning(
                "FINSPARK_MCP_TOKEN unset and debug=True; allowing anonymous MCP start-up"
            )
        return True
    return bool(token)


def enforce_or_exit() -> None:
    """Validate auth preconditions and abort with a clear error if unmet.

    Call this from the stdio entry point *before* ``server.run()``. The function
    writes a diagnostic message to stderr (so clients reading stdout for the
    MCP framing protocol see a clean failure) and exits with code 78
    (EX_CONFIG) when refusing to start.
    """
    if is_authenticated():
        return

    msg = (
        f"AdaptConfig MCP: {_TOKEN_ENV_VAR} is required when "
        "FINSPARK_DEBUG=false. Set the variable or enable debug mode."
    )
    print(msg, file=sys.stderr, flush=True)
    raise MCPAuthError(msg)
