"""Unit tests for the health check endpoints.

Tests use direct function calls with mocked DB sessions and settings
— no running server required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.responses import JSONResponse

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(raises: Exception | None = None) -> AsyncMock:
    """Return a mock AsyncSession whose execute() either succeeds or raises."""
    db = AsyncMock()
    if raises is not None:
        db.execute.side_effect = raises
    else:
        db.execute.return_value = MagicMock()
    return db


# ---------------------------------------------------------------------------
# readiness — database OK
# ---------------------------------------------------------------------------


async def test_readiness_db_ok_returns_200() -> None:
    from finspark.api.v1.endpoints.health import ComponentStatus, readiness

    db = _make_db()
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = "fake-key"

        result = await readiness(db)

    assert result.status == ComponentStatus.OK
    db_component = next(c for c in result.components if c.name == "database")
    assert db_component.status == ComponentStatus.OK
    assert db_component.latency_ms is not None
    assert db_component.latency_ms >= 0.0
    assert db_component.error is None


async def test_readiness_executes_select_1() -> None:
    from sqlalchemy import text

    from finspark.api.v1.endpoints.health import readiness

    db = _make_db()
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = "fake-key"

        await readiness(db)

    db.execute.assert_awaited_once()
    call_arg = db.execute.call_args[0][0]
    # sqlalchemy text() objects compare by string
    assert str(call_arg) == "SELECT 1"


# ---------------------------------------------------------------------------
# readiness — database DOWN
# ---------------------------------------------------------------------------


async def test_readiness_db_down_returns_503() -> None:
    from finspark.api.v1.endpoints.health import ComponentStatus, readiness

    db = _make_db(raises=OSError("connection refused"))
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = "fake-key"

        result = await readiness(db)

    # When DB is down the function returns a JSONResponse with 503
    assert isinstance(result, JSONResponse)
    assert result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    import json

    body = json.loads(result.body)
    assert body["status"] == ComponentStatus.DOWN
    db_component = next(c for c in body["components"] if c["name"] == "database")
    assert db_component["status"] == ComponentStatus.DOWN
    assert "connection refused" in db_component["error"]
    assert db_component["latency_ms"] is None


async def test_readiness_db_down_logs_error() -> None:
    from finspark.api.v1.endpoints.health import readiness

    db = _make_db(raises=RuntimeError("db gone"))
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = "fake-key"
        with patch("finspark.api.v1.endpoints.health.logger") as mock_logger:
            await readiness(db)

    mock_logger.error.assert_called_once_with("health_db_down", error="db gone")


# ---------------------------------------------------------------------------
# readiness — AI key checks
# ---------------------------------------------------------------------------


async def test_readiness_ai_ok_when_key_set() -> None:
    from finspark.api.v1.endpoints.health import ComponentStatus, readiness

    db = _make_db()
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = "AIzaSyFakeKey"

        result = await readiness(db)

    assert result.status == ComponentStatus.OK
    ai_component = next(c for c in result.components if c.name == "ai")
    assert ai_component.status == ComponentStatus.OK
    assert ai_component.error is None


async def test_readiness_ai_degraded_when_key_missing() -> None:
    from finspark.api.v1.endpoints.health import ComponentStatus, readiness

    db = _make_db()
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = ""

        result = await readiness(db)

    # Overall degrades to DEGRADED (not DOWN), still 200
    assert result.status == ComponentStatus.DEGRADED
    ai_component = next(c for c in result.components if c.name == "ai")
    assert ai_component.status == ComponentStatus.DEGRADED
    assert ai_component.error is not None
    assert "GEMINI_API_KEY" in ai_component.error


async def test_readiness_ai_degraded_logs_warning() -> None:
    from finspark.api.v1.endpoints.health import readiness

    db = _make_db()
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = "   "  # whitespace-only counts as missing
        with patch("finspark.api.v1.endpoints.health.logger") as mock_logger:
            await readiness(db)

    mock_logger.warning.assert_called_once_with("health_ai_key_missing")


async def test_readiness_db_down_takes_priority_over_ai_degraded() -> None:
    """When DB is DOWN, overall stays DOWN even if AI key is also missing."""
    from finspark.api.v1.endpoints.health import ComponentStatus, readiness

    import json

    db = _make_db(raises=OSError("no route to host"))
    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        mock_settings.GEMINI_API_KEY = ""

        result = await readiness(db)

    assert isinstance(result, JSONResponse)
    assert result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = json.loads(result.body)
    assert body["status"] == ComponentStatus.DOWN


# ---------------------------------------------------------------------------
# liveness — always 200, no DB
# ---------------------------------------------------------------------------


async def test_liveness_always_ok() -> None:
    from finspark.api.v1.endpoints.health import ComponentStatus, liveness

    with patch("finspark.api.v1.endpoints.health.settings") as mock_settings:
        mock_settings.APP_ENV = "development"

        result = await liveness()

    assert result.status == ComponentStatus.OK
    assert result.components == []
