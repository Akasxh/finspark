"""Reusable async HTTP client with retry logic."""

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class AsyncHTTPClient:
    """Thin wrapper around httpx.AsyncClient with retries."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "AsyncHTTPClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.get(path, **kwargs)
        response.raise_for_status()
        return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.post(path, **kwargs)
        response.raise_for_status()
        return response
