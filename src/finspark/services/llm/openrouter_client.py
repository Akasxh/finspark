"""Async OpenRouter LLM client using the OpenAI-compatible REST API via httpx.

Endpoint: https://openrouter.ai/api/v1/chat/completions
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from finspark.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """Thin async wrapper around the OpenRouter chat completions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or settings.openrouter_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key is not set. "
                "Set FINSPARK_OPENROUTER_API_KEY in .env or pass api_key explicitly."
            )

        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://adaptconfig-frontend-production.up.railway.app",
                "X-Title": "AdaptConfig",
            },
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_json: bool = False,
        model: str | None = None,
    ) -> str:
        """Send a prompt to OpenRouter and return the text response."""
        from finspark.services.llm.client import LLMAPIError

        url = f"{_BASE_URL}/chat/completions"
        effective_model = model or self.model

        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_json:
            body["response_format"] = {"type": "json_object"}

        try:
            resp = await self._client.post(url, json=body)
        except httpx.TimeoutException as exc:
            logger.error("openrouter_timeout model=%s", effective_model)
            raise LLMAPIError("OpenRouter API request timed out") from exc
        except httpx.NetworkError as exc:
            logger.error("openrouter_network_error model=%s error=%s", effective_model, exc)
            raise LLMAPIError(f"Network error communicating with OpenRouter: {exc}") from exc

        if resp.status_code != 200:
            safe_body = resp.text[:300]
            logger.error(
                "openrouter_api_error status=%s body=%s", resp.status_code, safe_body
            )
            raise LLMAPIError(
                f"OpenRouter API returned {resp.status_code}: {safe_body}"
            )

        data = resp.json()
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if not content:
                finish = choice.get("finish_reason", "")
                raise LLMAPIError(
                    f"Empty response from OpenRouter (finish_reason={finish})"
                )
            return content
        except (KeyError, IndexError) as exc:
            logger.error("openrouter_unexpected_response data=%s", data)
            raise LLMAPIError("Unexpected response structure from OpenRouter") from exc

    async def generate_json(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Generate and parse a JSON response from OpenRouter."""
        from finspark.services.llm.client import LLMAPIError

        text = await self.generate(
            prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            response_json=True,
            model=model,
        )
        # Claude (via OpenRouter) sometimes wraps JSON in markdown fences even with
        # response_format=json_object. Strip them defensively.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("openrouter_json_parse_error text=%s", text[:500])
            raise LLMAPIError(f"Failed to parse OpenRouter JSON response: {exc}") from exc
