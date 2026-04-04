"""
Integration tests: full workflow via httpx AsyncClient against the ASGI app.

Workflow steps covered:
1. Upload YAML document -> verify 202 + pending status
2. Get document detail -> verify 404 (stub: persistence not yet wired)
3. Generate config -> verify 202 + draft status + payload
4. Validate config -> verify 404 (stub: not yet wired)
5. Run simulation -> verify 202 + queued status
6. Delete document -> verify 404 (stub: not yet wired)
7. List audit log -> verify 200 + empty list (stub)

Tests are written against actual endpoint contracts and gracefully
handle stub responses so CI stays green while driving future implementation.
"""
from __future__ import annotations

import io
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.schemas.configurations import ConfigStatus
from finspark.schemas.documents import ParseStatus
from finspark.schemas.simulations import SimulationStatus

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_API = "/api/v1"


def _yaml_fixture_bytes() -> bytes:
    """Minimal OpenAPI YAML suitable for upload tests."""
    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/verify": {
                "post": {
                    "summary": "Verify",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "customer_id": {"type": "string"},
                                        "pan_number": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    return yaml.dump(spec).encode()


def _dev_tenant_id() -> str:
    return "00000000-0000-0000-0000-000000000001"


def _adapter_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Dedicated client fixture without conflicting Content-Type header
# ---------------------------------------------------------------------------
# The shared conftest `client` sets Content-Type: application/json globally
# which breaks multipart/form-data uploads.  This module-local fixture omits
# that default header so uploads work correctly.


@pytest_asyncio.fixture()
async def wf_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client for workflow tests.

    Shares the rolled-back DB session from conftest but does NOT set a global
    Content-Type header so that multipart file uploads negotiate their own
    boundary.
    """
    from finspark.api.deps import get_db
    from finspark.main import create_app

    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Step 1: Upload YAML file
# ---------------------------------------------------------------------------


class TestDocumentUpload:
    async def test_upload_yaml_returns_202(self, wf_client: AsyncClient) -> None:
        content = _yaml_fixture_bytes()
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("spec.yaml", io.BytesIO(content), "application/x-yaml")},
        )
        assert resp.status_code == 202, resp.text

    async def test_upload_yaml_response_has_id(self, wf_client: AsyncClient) -> None:
        content = _yaml_fixture_bytes()
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("spec.yaml", io.BytesIO(content), "application/x-yaml")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "id" in body
        parsed_id = uuid.UUID(body["id"])
        assert parsed_id is not None

    async def test_upload_yaml_has_pending_status(self, wf_client: AsyncClient) -> None:
        content = _yaml_fixture_bytes()
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("spec.yaml", io.BytesIO(content), "application/x-yaml")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == ParseStatus.PENDING

    async def test_upload_yaml_filename_preserved(self, wf_client: AsyncClient) -> None:
        content = _yaml_fixture_bytes()
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("my_api_spec.yaml", io.BytesIO(content), "application/x-yaml")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["filename"] == "my_api_spec.yaml"

    async def test_upload_yaml_size_bytes_populated(self, wf_client: AsyncClient) -> None:
        content = _yaml_fixture_bytes()
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("spec.yaml", io.BytesIO(content), "application/x-yaml")},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["size_bytes"] == len(content)

    async def test_upload_with_tags_and_description(self, wf_client: AsyncClient) -> None:
        content = _yaml_fixture_bytes()
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("spec.yaml", io.BytesIO(content), "application/x-yaml")},
            data={
                "tags": "credit,bureau,v2",
                "description": "CIBIL credit bureau API spec",
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["description"] == "CIBIL credit bureau API spec"
        assert "credit" in body["tags"]
        assert "bureau" in body["tags"]

    async def test_upload_unsupported_extension_returns_400(
        self, wf_client: AsyncClient
    ) -> None:
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("virus.exe", io.BytesIO(b"MZ\x90"), "application/octet-stream")},
        )
        assert resp.status_code == 400

    async def test_upload_empty_filename_returns_400(
        self, wf_client: AsyncClient
    ) -> None:
        content = _yaml_fixture_bytes()
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("", io.BytesIO(content), "application/x-yaml")},
        )
        assert resp.status_code in (400, 422)

    async def test_upload_pdf_returns_202(
        self, wf_client: AsyncClient, sample_pdf_bytes: bytes
    ) -> None:
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("brd.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
        )
        assert resp.status_code == 202

    async def test_upload_json_spec_returns_202(self, wf_client: AsyncClient) -> None:
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {},
        }
        resp = await wf_client.post(
            f"{_API}/documents/",
            files={
                "file": (
                    "api.json",
                    io.BytesIO(json.dumps(spec).encode()),
                    "application/json",
                )
            },
        )
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Step 2: Get document detail
# ---------------------------------------------------------------------------


class TestDocumentDetail:
    async def test_get_document_returns_404_stub(self, wf_client: AsyncClient) -> None:
        """The get_document endpoint is a stub; any ID returns 404 until persistence is wired."""
        doc_id = str(uuid.uuid4())
        resp = await wf_client.get(f"{_API}/documents/{doc_id}")
        assert resp.status_code == 404

    async def test_get_document_404_detail_contains_id(self, wf_client: AsyncClient) -> None:
        doc_id = str(uuid.uuid4())
        resp = await wf_client.get(f"{_API}/documents/{doc_id}")
        body = resp.json()
        assert "detail" in body
        assert doc_id in body["detail"]

    async def test_get_document_invalid_uuid_returns_422(
        self, wf_client: AsyncClient
    ) -> None:
        resp = await wf_client.get(f"{_API}/documents/not-a-valid-uuid")
        assert resp.status_code == 422

    async def test_list_documents_returns_200(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/documents/")
        assert resp.status_code == 200

    async def test_list_documents_paginated_response(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/documents/")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert isinstance(body["items"], list)


# ---------------------------------------------------------------------------
# Step 3: Generate config
# ---------------------------------------------------------------------------


class TestConfigGeneration:
    def _gen_payload(self) -> dict[str, Any]:
        return {
            "tenant_id": _dev_tenant_id(),
            "adapter_id": _adapter_id(),
            "document_ids": [],
            "overrides": {},
            "llm_hint": "",
        }

    async def test_generate_config_returns_202(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(
            f"{_API}/configurations/generate",
            json=self._gen_payload(),
        )
        assert resp.status_code == 202, resp.text

    async def test_generate_config_response_has_id(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(
            f"{_API}/configurations/generate",
            json=self._gen_payload(),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "id" in body
        assert uuid.UUID(body["id"]) is not None

    async def test_generate_config_status_is_draft(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(
            f"{_API}/configurations/generate",
            json=self._gen_payload(),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == ConfigStatus.DRAFT

    async def test_generate_config_payload_has_base_url(self, wf_client: AsyncClient) -> None:
        """Rule-based fallback payload must contain at minimum a base_url key."""
        resp = await wf_client.post(
            f"{_API}/configurations/generate",
            json=self._gen_payload(),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "payload" in body
        assert "base_url" in body["payload"]

    async def test_generate_config_payload_has_timeout_ms(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(
            f"{_API}/configurations/generate",
            json=self._gen_payload(),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "timeout_ms" in body["payload"]

    async def test_generate_config_tenant_id_preserved(self, wf_client: AsyncClient) -> None:
        payload = self._gen_payload()
        resp = await wf_client.post(f"{_API}/configurations/generate", json=payload)
        assert resp.status_code == 202
        body = resp.json()
        assert body["tenant_id"] == payload["tenant_id"]

    async def test_generate_config_missing_tenant_id_returns_422(
        self, wf_client: AsyncClient
    ) -> None:
        payload = {"adapter_id": _adapter_id()}
        resp = await wf_client.post(f"{_API}/configurations/generate", json=payload)
        assert resp.status_code == 422

    async def test_generate_config_with_llm_hint(self, wf_client: AsyncClient) -> None:
        payload = self._gen_payload()
        payload["llm_hint"] = "Use exponential backoff for retries"
        resp = await wf_client.post(f"{_API}/configurations/generate", json=payload)
        assert resp.status_code == 202

    async def test_list_configurations_returns_200(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/configurations/")
        assert resp.status_code == 200

    async def test_list_configurations_paginated(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/configurations/")
        body = resp.json()
        assert "items" in body
        assert "total" in body


# ---------------------------------------------------------------------------
# Step 4: Validate config
# ---------------------------------------------------------------------------


class TestConfigValidation:
    async def test_validate_nonexistent_config_returns_404(
        self, wf_client: AsyncClient
    ) -> None:
        config_id = str(uuid.uuid4())
        resp = await wf_client.post(f"{_API}/configurations/{config_id}/validate")
        assert resp.status_code == 404

    async def test_validate_invalid_uuid_returns_422(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(f"{_API}/configurations/not-a-uuid/validate")
        assert resp.status_code == 422

    async def test_get_nonexistent_config_returns_404(self, wf_client: AsyncClient) -> None:
        config_id = str(uuid.uuid4())
        resp = await wf_client.get(f"{_API}/configurations/{config_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Step 5: Run simulation
# ---------------------------------------------------------------------------


class TestSimulationRun:
    def _sim_payload(self) -> dict[str, Any]:
        return {
            "tenant_id": _dev_tenant_id(),
            "config_id": _adapter_id(),
            "scenario": "default",
            "payload_override": {},
            "assertions": [],
            "timeout_seconds": 30,
            "mock_external": True,
        }

    async def test_run_simulation_returns_202(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(
            f"{_API}/simulations/",
            json=self._sim_payload(),
        )
        assert resp.status_code == 202, resp.text

    async def test_run_simulation_status_is_queued(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(
            f"{_API}/simulations/",
            json=self._sim_payload(),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == SimulationStatus.QUEUED

    async def test_run_simulation_response_has_id(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.post(
            f"{_API}/simulations/",
            json=self._sim_payload(),
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "id" in body
        assert uuid.UUID(body["id"]) is not None

    async def test_run_simulation_tenant_id_preserved(self, wf_client: AsyncClient) -> None:
        payload = self._sim_payload()
        resp = await wf_client.post(f"{_API}/simulations/", json=payload)
        assert resp.status_code == 202
        body = resp.json()
        assert body["tenant_id"] == payload["tenant_id"]

    async def test_run_simulation_missing_required_fields_returns_422(
        self, wf_client: AsyncClient
    ) -> None:
        resp = await wf_client.post(f"{_API}/simulations/", json={})
        assert resp.status_code == 422

    async def test_get_simulation_status_returns_404(self, wf_client: AsyncClient) -> None:
        sim_id = str(uuid.uuid4())
        resp = await wf_client.get(f"{_API}/simulations/{sim_id}")
        assert resp.status_code == 404

    async def test_list_simulations_returns_200(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/simulations/")
        assert resp.status_code == 200

    async def test_simulation_with_custom_scenario(self, wf_client: AsyncClient) -> None:
        payload = self._sim_payload()
        payload["scenario"] = "error_scenario"
        resp = await wf_client.post(f"{_API}/simulations/", json=payload)
        assert resp.status_code == 202
        body = resp.json()
        assert body["scenario"] == "error_scenario"


# ---------------------------------------------------------------------------
# Step 6: Delete document
# ---------------------------------------------------------------------------


class TestDocumentDelete:
    async def test_delete_document_returns_404_stub(self, wf_client: AsyncClient) -> None:
        """Stub: delete always returns 404 until persistence is wired."""
        doc_id = str(uuid.uuid4())
        resp = await wf_client.delete(f"{_API}/documents/{doc_id}")
        assert resp.status_code == 404

    async def test_delete_document_invalid_uuid_returns_422(
        self, wf_client: AsyncClient
    ) -> None:
        resp = await wf_client.delete(f"{_API}/documents/bad-uuid")
        assert resp.status_code == 422

    async def test_delete_route_exists(self, wf_client: AsyncClient) -> None:
        """Route must exist — 404 means not found, not 405 method not allowed."""
        doc_id = str(uuid.uuid4())
        resp = await wf_client.delete(f"{_API}/documents/{doc_id}")
        assert resp.status_code != 405, "DELETE /documents/{id} route not registered"


# ---------------------------------------------------------------------------
# Step 7: Audit log
# ---------------------------------------------------------------------------


class TestAuditLog:
    async def test_list_audit_log_returns_200(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/audit/")
        assert resp.status_code == 200

    async def test_list_audit_log_has_paginated_shape(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/audit/")
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert isinstance(body["items"], list)

    async def test_list_audit_log_page_defaults_to_one(self, wf_client: AsyncClient) -> None:
        resp = await wf_client.get(f"{_API}/audit/")
        body = resp.json()
        assert body["page"] == 1

    async def test_audit_query_with_filters_returns_200(
        self, wf_client: AsyncClient
    ) -> None:
        resp = await wf_client.get(
            f"{_API}/audit/",
            params={"resource_type": "document", "action": "delete"},
        )
        assert resp.status_code == 200

    async def test_audit_query_invalid_action_returns_422(
        self, wf_client: AsyncClient
    ) -> None:
        resp = await wf_client.get(
            f"{_API}/audit/",
            params={"action": "unknown_action_xyz"},
        )
        assert resp.status_code == 422

    async def test_get_single_audit_entry_returns_404(
        self, wf_client: AsyncClient
    ) -> None:
        audit_id = str(uuid.uuid4())
        resp = await wf_client.get(f"{_API}/audit/{audit_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Full workflow (sequential scenario)
# ---------------------------------------------------------------------------


class TestFullWorkflowSequential:
    """
    Exercises the full workflow in order: upload -> generate -> simulate.

    Verifies that each step returns the correct status code and response shape
    even when later steps are stubs returning 404.
    """

    async def test_upload_then_generate_config_workflow(
        self, wf_client: AsyncClient
    ) -> None:
        # Step 1: Upload
        content = _yaml_fixture_bytes()
        upload_resp = await wf_client.post(
            f"{_API}/documents/",
            files={"file": ("spec.yaml", io.BytesIO(content), "application/x-yaml")},
        )
        assert upload_resp.status_code == 202
        doc_body = upload_resp.json()
        assert doc_body["status"] == ParseStatus.PENDING
        doc_id = doc_body["id"]

        # Step 2: Attempt to get document detail (stub returns 404)
        detail_resp = await wf_client.get(f"{_API}/documents/{doc_id}")
        assert detail_resp.status_code == 404  # stub; will be 200 when persistence lands

        # Step 3: Generate config (using the document ID)
        gen_payload = {
            "tenant_id": _dev_tenant_id(),
            "adapter_id": _adapter_id(),
            "document_ids": [doc_id],
            "overrides": {},
            "llm_hint": "map pan_number to bureau.pan",
        }
        gen_resp = await wf_client.post(
            f"{_API}/configurations/generate",
            json=gen_payload,
        )
        assert gen_resp.status_code == 202
        config_body = gen_resp.json()
        assert config_body["status"] == ConfigStatus.DRAFT
        config_id = config_body["id"]

        # Step 4: Validate config (stub returns 404)
        val_resp = await wf_client.post(f"{_API}/configurations/{config_id}/validate")
        assert val_resp.status_code == 404  # stub

        # Step 5: Run simulation
        sim_payload = {
            "tenant_id": _dev_tenant_id(),
            "config_id": config_id,
            "scenario": "default",
            "payload_override": {},
            "assertions": [],
            "timeout_seconds": 30,
            "mock_external": True,
        }
        sim_resp = await wf_client.post(f"{_API}/simulations/", json=sim_payload)
        assert sim_resp.status_code == 202
        sim_body = sim_resp.json()
        assert sim_body["status"] == SimulationStatus.QUEUED

        # Step 6: Delete document (stub returns 404)
        del_resp = await wf_client.delete(f"{_API}/documents/{doc_id}")
        assert del_resp.status_code == 404  # stub

        # Step 7: Audit log (stub returns empty list)
        audit_resp = await wf_client.get(f"{_API}/audit/")
        assert audit_resp.status_code == 200
        audit_body = audit_resp.json()
        assert isinstance(audit_body["items"], list)

    async def test_upload_multiple_documents_list_returns_200(
        self, wf_client: AsyncClient
    ) -> None:
        content = _yaml_fixture_bytes()
        for i in range(3):
            resp = await wf_client.post(
                f"{_API}/documents/",
                files={
                    "file": (
                        f"spec_{i}.yaml",
                        io.BytesIO(content),
                        "application/x-yaml",
                    )
                },
            )
            assert resp.status_code == 202

        list_resp = await wf_client.get(f"{_API}/documents/")
        assert list_resp.status_code == 200

    async def test_generate_config_rule_based_when_ai_disabled(
        self, wf_client: AsyncClient
    ) -> None:
        """
        When AI is disabled (no GEMINI_API_KEY), the endpoint falls back to
        rule-based generation. The response must still be 202 with a draft config.
        """
        payload = {
            "tenant_id": _dev_tenant_id(),
            "adapter_id": _adapter_id(),
            "document_ids": [],
            "overrides": {},
            "llm_hint": "",
        }
        resp = await wf_client.post(f"{_API}/configurations/generate", json=payload)
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == ConfigStatus.DRAFT
        assert "_generation_method" in body["payload"]
        assert body["payload"]["_generation_method"] in ("rule_based", "llm")
