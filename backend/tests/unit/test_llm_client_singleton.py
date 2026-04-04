"""Tests for LLM client singleton, async safety, close, and reset."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest

from finspark.services.llm.client import GeminiClient, get_llm_client, reset_client


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure cache is cleared before and after every test."""
    reset_client()
    yield
    reset_client()


class TestSingleton:
    def test_get_llm_client_returns_gemini_client(self) -> None:
        with patch("finspark.services.llm.client.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
            client = get_llm_client()
        assert isinstance(client, GeminiClient)

    def test_singleton_same_instance(self) -> None:
        with patch("finspark.services.llm.client.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
            client_a = get_llm_client()
            client_b = get_llm_client()
        assert client_a is client_b

    def test_reset_clears_cache(self) -> None:
        with patch("finspark.services.llm.client.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
            client_a = get_llm_client()
            reset_client()
            client_b = get_llm_client()
        assert client_a is not client_b

    def test_http_client_created_once_in_init(self) -> None:
        with patch("finspark.services.llm.client.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
            client = get_llm_client()
        assert isinstance(client._http_client, httpx.AsyncClient)
        # Same instance on repeated access
        assert client._http_client is get_llm_client()._http_client


class TestAsyncSafety:
    async def test_concurrent_calls_return_same_instance(self) -> None:
        """Multiple coroutines racing to call get_llm_client() get the same object."""
        with patch("finspark.services.llm.client.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_settings.GEMINI_MODEL = "gemini-2.5-flash"

            async def fetch() -> GeminiClient:
                return get_llm_client()

            results = await asyncio.gather(*[fetch() for _ in range(20)])

        first = results[0]
        assert all(r is first for r in results)

    async def test_close_method_exists_and_is_awaitable(self) -> None:
        with patch("finspark.services.llm.client.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_settings.GEMINI_MODEL = "gemini-2.5-flash"
            client = GeminiClient(api_key="test-key", model="gemini-2.5-flash")

        # close() should be awaitable and not raise
        await client.close()

    async def test_close_closes_http_client(self) -> None:
        client = GeminiClient(api_key="test-key", model="gemini-2.5-flash")
        assert not client._http_client.is_closed
        await client.close()
        assert client._http_client.is_closed
