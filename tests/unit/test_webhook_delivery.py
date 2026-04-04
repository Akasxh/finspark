"""Unit tests for the webhook delivery service."""

import hashlib
import hmac
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finspark.core.security import encrypt_value
from finspark.models.webhook import Webhook, WebhookDelivery
from finspark.services.webhook_delivery import _send_webhook, deliver_event


def _make_webhook(
    tenant_id: str = "tenant-1",
    url: str = "https://example.com/hook",
    events: list[str] | None = None,
    secret: str = "my-secret",
    is_active: bool = True,
) -> Webhook:
    wh = Webhook(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        url=url,
        secret=encrypt_value(secret),
        events=json.dumps(events or ["config.created"]),
        is_active=is_active,
    )
    return wh


def _make_mock_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


class TestDeliverEvent:
    @pytest.mark.asyncio
    async def test_deliver_event_calls_matching_webhook(self) -> None:
        wh = _make_webhook(events=["config.created"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch(
            "finspark.services.webhook_delivery.async_session_factory"
        ) as mock_factory:
            mock_db = _make_mock_db()
            # scalars().all() returns our webhook
            mock_db.execute = AsyncMock(
                return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[wh]))))
            )
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_http = AsyncMock()
                mock_http.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await deliver_event("tenant-1", "config.created", {"key": "val"})

            mock_http.post.assert_awaited_once()
            call_args = mock_http.post.call_args
            assert call_args[0][0] == wh.url

    @pytest.mark.asyncio
    async def test_deliver_event_skips_non_matching_event(self) -> None:
        wh = _make_webhook(events=["config.updated"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch(
            "finspark.services.webhook_delivery.async_session_factory"
        ) as mock_factory:
            mock_db = _make_mock_db()
            mock_db.execute = AsyncMock(
                return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[wh]))))
            )
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_http = AsyncMock()
                mock_http.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await deliver_event("tenant-1", "config.created", {"key": "val"})

            # config.created does not match config.updated → no HTTP call
            mock_http.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deliver_event_wildcard_matches_any_event(self) -> None:
        wh = _make_webhook(events=["*"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch(
            "finspark.services.webhook_delivery.async_session_factory"
        ) as mock_factory:
            mock_db = _make_mock_db()
            mock_db.execute = AsyncMock(
                return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[wh]))))
            )
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_http = AsyncMock()
                mock_http.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await deliver_event("tenant-1", "simulation.completed", {"id": "x"})

            mock_http.post.assert_awaited_once()


class TestSendWebhook:
    @pytest.mark.asyncio
    async def test_hmac_signature_is_correct(self) -> None:
        """Verify X-Webhook-Signature header is sha256=<hex> of the body."""
        wh = _make_webhook(secret="supersecret")
        mock_db = _make_mock_db()

        captured_headers: dict[str, str] = {}
        captured_body: str | bytes = b""

        async def fake_post(url: str, content: str | bytes, headers: dict[str, str]) -> Any:
            nonlocal captured_headers, captured_body
            captured_headers = headers
            captured_body = content
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _send_webhook(mock_db, wh, "config.created", {"id": "abc"})

        assert "X-Webhook-Signature" in captured_headers
        sig_header = captured_headers["X-Webhook-Signature"]
        assert sig_header.startswith("sha256=")
        body_bytes = captured_body if isinstance(captured_body, bytes) else captured_body.encode()
        expected_sig = hmac.new(
            b"supersecret", body_bytes, hashlib.sha256
        ).hexdigest()
        assert sig_header == f"sha256={expected_sig}"

    @pytest.mark.asyncio
    async def test_delivery_status_is_delivered_on_2xx(self) -> None:
        wh = _make_webhook()
        mock_db = _make_mock_db()

        mock_resp = MagicMock()
        mock_resp.status_code = 201

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _send_webhook(mock_db, wh, "config.created", {})

        # Grab the WebhookDelivery that was passed to db.add
        added = mock_db.add.call_args[0][0]
        assert isinstance(added, WebhookDelivery)
        assert added.status == "delivered"
        assert added.response_code == 201
        assert added.attempts == 1

    @pytest.mark.asyncio
    async def test_delivery_status_is_failed_after_max_attempts(self) -> None:
        import httpx as _httpx

        wh = _make_webhook()
        mock_db = _make_mock_db()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(
                side_effect=_httpx.RequestError("timeout", request=MagicMock())
            )
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _send_webhook(mock_db, wh, "config.created", {})

        added = mock_db.add.call_args[0][0]
        assert added.status == "failed"
        assert added.attempts == 3  # max_attempts exhausted

    @pytest.mark.asyncio
    async def test_delivery_record_is_persisted(self) -> None:
        wh = _make_webhook()
        mock_db = _make_mock_db()

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _send_webhook(mock_db, wh, "config.created", {"foo": "bar"})

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        added = mock_db.add.call_args[0][0]
        assert added.webhook_id == wh.id
        assert added.event_type == "config.created"
        parsed = json.loads(added.payload)
        assert parsed["data"] == {"foo": "bar"}
        assert parsed["event"] == "config.created"

    @pytest.mark.asyncio
    async def test_no_signature_header_when_secret_missing(self) -> None:
        wh = _make_webhook()
        wh.secret = ""  # no secret
        mock_db = _make_mock_db()

        captured_headers: dict[str, str] = {}

        async def fake_post(url: str, content: str | bytes, headers: dict[str, str]) -> Any:
            nonlocal captured_headers
            captured_headers = headers
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.post = fake_post
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await _send_webhook(mock_db, wh, "config.created", {})

        assert "X-Webhook-Signature" not in captured_headers
