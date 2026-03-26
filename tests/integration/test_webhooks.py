"""Integration tests for webhook management endpoints."""

import pytest
from httpx import AsyncClient


class TestWebhookCRUD:
    @pytest.mark.asyncio
    async def test_register_webhook(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/webhooks/",
            json={
                "url": "https://example.com/hook",
                "secret": "my-secret-key",
                "events": ["config.created", "config.updated"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["url"] == "https://example.com/hook"
        assert data["data"]["events"] == ["config.created", "config.updated"]
        assert data["data"]["is_active"] is True
        assert "secret" not in data["data"]

    @pytest.mark.asyncio
    async def test_list_webhooks(self, client: AsyncClient) -> None:
        # Create two webhooks
        await client.post(
            "/api/v1/webhooks/",
            json={"url": "https://example.com/hook1", "secret": "s1", "events": ["a"]},
        )
        await client.post(
            "/api/v1/webhooks/",
            json={"url": "https://example.com/hook2", "secret": "s2", "events": ["b"]},
        )

        response = await client.get("/api/v1/webhooks/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2

    @pytest.mark.asyncio
    async def test_delete_webhook(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/webhooks/",
            json={"url": "https://example.com/hook", "secret": "s", "events": []},
        )
        webhook_id = create_resp.json()["data"]["id"]

        del_resp = await client.delete(f"/api/v1/webhooks/{webhook_id}")
        assert del_resp.status_code == 200

        list_resp = await client.get("/api/v1/webhooks/")
        assert len(list_resp.json()["data"]) == 0

    @pytest.mark.asyncio
    async def test_delete_webhook_not_found(self, client: AsyncClient) -> None:
        response = await client.delete("/api/v1/webhooks/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_test_webhook(self, client: AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/webhooks/",
            json={"url": "https://example.com/hook", "secret": "s", "events": ["webhook.test"]},
        )
        webhook_id = create_resp.json()["data"]["id"]

        test_resp = await client.post(f"/api/v1/webhooks/{webhook_id}/test")
        assert test_resp.status_code == 200
        data = test_resp.json()
        assert data["success"] is True
        assert data["data"]["event_type"] == "webhook.test"
        assert data["data"]["status"] == "delivered"
        assert data["data"]["response_code"] == 200
        assert data["data"]["attempts"] == 1

    @pytest.mark.asyncio
    async def test_test_webhook_not_found(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/webhooks/nonexistent-id/test")
        assert response.status_code == 404
