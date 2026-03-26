"""
Unit tests for the Auto-Configuration Engine.

Covers:
- Config generation from LLM output + adapter registry
- Config diff (old vs new version)
- Validation: required fields, invalid types
- Credential masking in serialised output
- Rollback plan generation
- Config version stamping
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _get_engine():
    try:
        from app.services.config_engine import ConfigEngine  # type: ignore[import]

        return ConfigEngine
    except ImportError:
        pytest.skip("app.services.config_engine not yet implemented")


def _get_schema():
    try:
        from app.schemas.config import IntegrationConfigSchema  # type: ignore[import]

        return IntegrationConfigSchema
    except ImportError:
        pytest.skip("app.schemas.config not yet implemented")


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


class TestConfigGeneration:
    def test_generates_config_from_llm_output(self, mock_llm_response: dict[str, Any]) -> None:
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        configs = engine.build_from_llm_output(mock_llm_response, tenant_id="tenant-abc")
        assert len(configs) == len(mock_llm_response["adapters"])
        first = configs[0]
        assert first["adapter_id"] == "cibil-bureau"
        assert first["timeout_ms"] == 3000
        assert first["retry_count"] == 3

    def test_config_includes_tenant_id(self, mock_llm_response: dict[str, Any]) -> None:
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        configs = engine.build_from_llm_output(mock_llm_response, tenant_id="tenant-xyz")
        for cfg in configs:
            assert cfg["tenant_id"] == "tenant-xyz"

    def test_config_version_is_stamped(self, mock_llm_response: dict[str, Any]) -> None:
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        configs = engine.build_from_llm_output(mock_llm_response, tenant_id="t1")
        for cfg in configs:
            assert "version" in cfg
            assert "created_at" in cfg

    def test_credentials_not_in_plain_config(self, mock_llm_response: dict[str, Any]) -> None:
        """Credentials must be vault references, never inline."""
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        configs = engine.build_from_llm_output(mock_llm_response, tenant_id="t1")
        serialised = json.dumps(configs)
        assert "api_key_value" not in serialised
        assert "password" not in serialised.lower()


# ---------------------------------------------------------------------------
# Config diff
# ---------------------------------------------------------------------------


class TestConfigDiff:
    def test_diff_detects_timeout_change(self) -> None:
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        old = {"timeout_ms": 3000, "retry_count": 3, "base_url": "https://old.example.com"}
        new = {"timeout_ms": 5000, "retry_count": 3, "base_url": "https://old.example.com"}
        diff = engine.compute_diff(old, new)
        assert any(d["field"] == "timeout_ms" for d in diff)
        changed = next(d for d in diff if d["field"] == "timeout_ms")
        assert changed["old"] == 3000
        assert changed["new"] == 5000

    def test_diff_empty_when_identical(self) -> None:
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        cfg = {"timeout_ms": 3000, "retry_count": 3}
        assert engine.compute_diff(cfg, cfg) == []

    def test_diff_detects_added_field(self) -> None:
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        old = {"timeout_ms": 3000}
        new = {"timeout_ms": 3000, "retry_count": 3}
        diff = engine.compute_diff(old, new)
        added = [d for d in diff if d.get("op") == "add"]
        assert any(d["field"] == "retry_count" for d in added)

    def test_rollback_plan_is_valid(self) -> None:
        ConfigEngine = _get_engine()
        engine = ConfigEngine()
        old = {"timeout_ms": 3000, "retry_count": 3}
        new = {"timeout_ms": 5000, "retry_count": 5}
        rollback = engine.generate_rollback_plan(old_config=old, new_config=new)
        assert rollback["target_config"] == old
        assert "reason" in rollback


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_validates_required_base_url(self) -> None:
        try:
            from app.schemas.config import IntegrationConfigSchema  # type: ignore[import]
            from pydantic import ValidationError
        except ImportError:
            pytest.skip()

        with pytest.raises(ValidationError):
            IntegrationConfigSchema(
                adapter_id="cibil-bureau",
                tenant_id="t1",
                adapter_version="2.0",
                # base_url intentionally omitted
                timeout_ms=3000,
                retry_count=3,
            )

    def test_validates_positive_timeout(self) -> None:
        try:
            from app.schemas.config import IntegrationConfigSchema  # type: ignore[import]
            from pydantic import ValidationError
        except ImportError:
            pytest.skip()

        with pytest.raises(ValidationError):
            IntegrationConfigSchema(
                adapter_id="cibil-bureau",
                tenant_id="t1",
                adapter_version="2.0",
                base_url="https://api.example.com",
                timeout_ms=-1,
                retry_count=3,
            )

    def test_valid_config_passes(self) -> None:
        try:
            from app.schemas.config import IntegrationConfigSchema  # type: ignore[import]
        except ImportError:
            pytest.skip()

        cfg = IntegrationConfigSchema(
            adapter_id="cibil-bureau",
            tenant_id="t1",
            adapter_version="2.0",
            base_url="https://api.cibil.example.com",
            timeout_ms=3000,
            retry_count=3,
        )
        assert cfg.adapter_id == "cibil-bureau"


# ---------------------------------------------------------------------------
# LLM integration (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_engine_calls_llm(
    mock_openai: AsyncMock,
    sample_brd_text: str,
) -> None:
    """ConfigEngine.generate_from_document should call the LLM exactly once."""
    try:
        from app.services.config_engine import ConfigEngine  # type: ignore[import]
    except ImportError:
        pytest.skip()

    engine = ConfigEngine(llm_client=mock_openai)
    await engine.generate_from_document(text=sample_brd_text, tenant_id="t1")
    mock_openai.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_config_engine_retries_on_llm_json_error(
    mock_openai: AsyncMock,
) -> None:
    """If the LLM returns malformed JSON on first call, engine should retry."""
    try:
        from app.services.config_engine import ConfigEngine  # type: ignore[import]
    except ImportError:
        pytest.skip()

    bad_response = MagicMock()
    bad_response.choices = [MagicMock(message=MagicMock(content="not json {{{{"))]

    good_response = MagicMock()
    good_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps({"adapters": [], "field_mappings": [], "config_diff": []})
            )
        )
    ]
    mock_openai.chat.completions.create = AsyncMock(
        side_effect=[bad_response, good_response]
    )

    engine = ConfigEngine(llm_client=mock_openai)
    result = await engine.generate_from_document(text="some brd", tenant_id="t1")
    assert isinstance(result, dict)
    assert mock_openai.chat.completions.create.await_count == 2
