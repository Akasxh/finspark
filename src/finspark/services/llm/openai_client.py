"""Async OpenAI LLM client (GPT-5 family) using the chat completions REST API.

Endpoint: https://api.openai.com/v1/chat/completions

Notes vs the OpenRouterClient:
- Uses `max_completion_tokens` (not `max_tokens`). GPT-5 reasoning models reject the
  legacy field.
- GPT-5 (`gpt-5`, `gpt-5-mini`) are reasoning models that consume tokens internally
  before producing output. Default budget is generous (8192) so structured JSON has
  room to complete after the reasoning pass.
- GPT-5 reasoning models only support the default temperature (1.0); we omit
  `temperature` from the body so we don't get a 400 from the API.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from finspark.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openai.com/v1"

# Models that are reasoning-only and reject temperature/non-default sampling params.
# Any model id that starts with one of these prefixes is treated as a reasoning model.
_REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_MODEL_PREFIXES)


class OpenAIClient:
    """Thin async wrapper around the OpenAI chat completions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "OpenAI API key is not set. "
                "Set FINSPARK_OPENAI_API_KEY in .env or pass api_key explicitly."
            )

        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
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
        """Send a prompt to OpenAI and return the text response."""
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
            "max_completion_tokens": max_tokens,
        }

        # Reasoning models only accept the default temperature — omit the field entirely
        # rather than send a value the API will reject.
        if not _is_reasoning_model(effective_model):
            body["temperature"] = temperature

        if response_json:
            body["response_format"] = {"type": "json_object"}

        try:
            resp = await self._client.post(url, json=body)
        except httpx.TimeoutException as exc:
            logger.error("openai_timeout model=%s", effective_model)
            raise LLMAPIError("OpenAI API request timed out") from exc
        except httpx.NetworkError as exc:
            logger.error("openai_network_error model=%s error=%s", effective_model, exc)
            raise LLMAPIError(f"Network error communicating with OpenAI: {exc}") from exc

        if resp.status_code != 200:
            safe_body = resp.text[:300]
            logger.error(
                "openai_api_error status=%s body=%s", resp.status_code, safe_body
            )
            raise LLMAPIError(
                f"OpenAI API returned {resp.status_code}: {safe_body}"
            )

        data = resp.json()
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if not content:
                finish = choice.get("finish_reason", "")
                # GPT-5 with too-low max_completion_tokens returns empty + finish=length
                # because reasoning consumed the entire budget. Surface this clearly.
                raise LLMAPIError(
                    f"Empty response from OpenAI (finish_reason={finish}, model={effective_model}). "
                    "If finish_reason=length, increase max_tokens — reasoning models need headroom."
                )
            return content
        except (KeyError, IndexError) as exc:
            logger.error("openai_unexpected_response data=%s", data)
            raise LLMAPIError("Unexpected response structure from OpenAI") from exc

    async def generate_json(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Generate and parse a JSON response from OpenAI."""
        from finspark.services.llm.client import LLMAPIError

        text = await self.generate(
            prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens,
            response_json=True,
            model=model,
        )
        # OpenAI's json_object response_format is strict; we still strip
        # markdown fences defensively in case a fine-tune or future model wraps them.
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
            logger.error("openai_json_parse_error text=%s", text[:500])
            raise LLMAPIError(f"Failed to parse OpenAI JSON response: {exc}") from exc
