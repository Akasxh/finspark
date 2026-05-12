"""Unit tests for the security inspector rule engine and report assembly."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from finspark.services.security.inspector import SecurityInspector


@pytest.fixture
def inspector() -> SecurityInspector:
    return SecurityInspector()


# ---------------------------------------------------------------------------
# Rule: No auth declared -> API2 critical
# ---------------------------------------------------------------------------

class TestNoAuth:
    @pytest.mark.asyncio
    async def test_no_auth_triggers_critical(self, inspector: SecurityInspector):
        spec = "openapi: '3.0.3'\ninfo:\n  title: Test\n  version: '1.0'\npaths:\n  /items:\n    get:\n      summary: list"
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title for f in report.findings]
        assert "No authentication declared" in titles
        finding = next(f for f in report.findings if f.title == "No authentication declared")
        assert finding.severity == "critical"
        assert finding.category == "API2_Broken_Authentication"

    @pytest.mark.asyncio
    async def test_auth_present_no_finding(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
security:
  - ApiKey: []
components:
  securitySchemes:
    ApiKey:
      type: apiKey
      in: header
      name: X-API-Key
paths:
  /items:
    get:
      summary: list
"""
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title for f in report.findings]
        assert "No authentication declared" not in titles


# ---------------------------------------------------------------------------
# Rule: HTTP base URL -> API8 high
# ---------------------------------------------------------------------------

class TestHttpBaseUrl:
    @pytest.mark.asyncio
    async def test_http_url_triggers_high(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
servers:
  - url: http://api.example.com/v1
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if f.title == "HTTP base URL (no TLS)"), None
        )
        assert finding is not None
        assert finding.severity == "high"

    @pytest.mark.asyncio
    async def test_https_url_no_finding(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
servers:
  - url: https://api.example.com/v1
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title for f in report.findings]
        assert "HTTP base URL (no TLS)" not in titles


# ---------------------------------------------------------------------------
# Rule: Credentials in query string -> API2 high
# ---------------------------------------------------------------------------

class TestCredentialsInUrl:
    @pytest.mark.asyncio
    async def test_query_apikey_triggers(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
security:
  - QueryKey: []
components:
  securitySchemes:
    QueryKey:
      type: apiKey
      in: query
      name: api_key
paths:
  /data:
    get:
      summary: get data
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "credentials in query" in f.title.lower()), None
        )
        assert finding is not None
        assert finding.severity == "high"

    @pytest.mark.asyncio
    async def test_header_apikey_no_finding(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
security:
  - HeaderKey: []
components:
  securitySchemes:
    HeaderKey:
      type: apiKey
      in: header
      name: X-API-Key
paths:
  /data:
    get:
      summary: get data
"""
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title.lower() for f in report.findings]
        assert not any("credentials in query" in t for t in titles)


# ---------------------------------------------------------------------------
# Rule: Sensitive fields in URL path -> API3 high
# ---------------------------------------------------------------------------

class TestSensitivePathParams:
    @pytest.mark.asyncio
    async def test_pan_in_path(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
paths:
  /users/{pan}/score:
    get:
      summary: get score by PAN
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "Sensitive field in URL path" in f.title), None
        )
        assert finding is not None
        assert finding.severity == "high"
        assert "pan" in finding.description.lower()

    @pytest.mark.asyncio
    async def test_aadhaar_in_path(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
paths:
  /verify/{aadhaar}:
    post:
      summary: verify aadhaar
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "Sensitive field in URL path" in f.title), None
        )
        assert finding is not None

    @pytest.mark.asyncio
    async def test_password_in_path(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
paths:
  /reset-password/{token}:
    post:
      summary: reset password
"""
        report = await inspector.inspect_api_spec(spec)
        sensitive_findings = [
            f for f in report.findings if "Sensitive field in URL path" in f.title
        ]
        # Both 'password' and 'token' match
        assert len(sensitive_findings) >= 1


# ---------------------------------------------------------------------------
# Rule: Wildcard CORS -> API8 medium
# ---------------------------------------------------------------------------

class TestWildcardCors:
    @pytest.mark.asyncio
    async def test_wildcard_cors(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
  description: "Sets Access-Control-Allow-Origin: *"
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "Wildcard CORS" in f.title), None
        )
        assert finding is not None
        assert finding.severity == "medium"


# ---------------------------------------------------------------------------
# Rule: No rate limiting -> API4 medium
# ---------------------------------------------------------------------------

class TestNoRateLimiting:
    @pytest.mark.asyncio
    async def test_no_rate_limit_mentioned(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
paths:
  /data:
    get:
      summary: get data
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "rate limiting" in f.title.lower()), None
        )
        assert finding is not None
        assert finding.severity == "medium"

    @pytest.mark.asyncio
    async def test_rate_limit_present_no_finding(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
  description: "Rate limits: 100 requests/minute. Returns 429 when exceeded."
paths:
  /data:
    get:
      summary: get data
      responses:
        '429':
          description: Too Many Requests
"""
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title.lower() for f in report.findings]
        assert not any("rate limiting" in t for t in titles)


# ---------------------------------------------------------------------------
# Rule: Plaintext password field -> API2 medium
# ---------------------------------------------------------------------------

class TestPlaintextPassword:
    @pytest.mark.asyncio
    async def test_password_without_format(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
components:
  schemas:
    LoginRequest:
      type: object
      properties:
        username:
          type: string
        password:
          type: string
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "Plaintext password" in f.title), None
        )
        assert finding is not None
        assert finding.severity == "medium"

    @pytest.mark.asyncio
    async def test_password_with_format_no_finding(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
components:
  schemas:
    LoginRequest:
      type: object
      properties:
        password:
          type: string
          format: password
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title for f in report.findings]
        assert "Plaintext password field" not in titles


# ---------------------------------------------------------------------------
# Rule: Old TLS version -> API8 high
# ---------------------------------------------------------------------------

class TestOldTls:
    @pytest.mark.asyncio
    async def test_tls10_triggers(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
  description: "Supports TLSv1.0 and TLSv1.2"
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "Deprecated TLS" in f.title), None
        )
        assert finding is not None
        assert finding.severity == "high"

    @pytest.mark.asyncio
    async def test_tls12_only_no_finding(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
  description: "Requires TLSv1.2 or higher"
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title for f in report.findings]
        assert "Deprecated TLS version referenced" not in titles


# ---------------------------------------------------------------------------
# Rule: Hardcoded API key in example -> API2 high
# ---------------------------------------------------------------------------

class TestHardcodedApiKey:
    @pytest.mark.asyncio
    async def test_example_with_key_pattern(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
components:
  schemas:
    AuthRequest:
      type: object
      properties:
        api_token:
          type: string
          example: "sk-live-abc123def456ghi789jkl012"
paths: {}
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "Hardcoded API key" in f.title), None
        )
        assert finding is not None
        assert finding.severity == "high"


# ---------------------------------------------------------------------------
# Rule: Missing API versioning -> API9 low
# ---------------------------------------------------------------------------

class TestMissingVersioning:
    @pytest.mark.asyncio
    async def test_no_version_in_path(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
servers:
  - url: https://api.example.com
paths:
  /items:
    get:
      summary: list items
"""
        report = await inspector.inspect_api_spec(spec)
        finding = next(
            (f for f in report.findings if "Missing API versioning" in f.title), None
        )
        assert finding is not None
        assert finding.severity == "low"

    @pytest.mark.asyncio
    async def test_versioned_path_no_finding(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
servers:
  - url: https://api.example.com/v1
paths:
  /items:
    get:
      summary: list items
"""
        report = await inspector.inspect_api_spec(spec)
        titles = [f.title for f in report.findings]
        assert "Missing API versioning in paths" not in titles


# ---------------------------------------------------------------------------
# LLM path with mock
# ---------------------------------------------------------------------------

class TestLlmAnalysis:
    @pytest.mark.asyncio
    async def test_llm_augments_findings(self, inspector: SecurityInspector):
        mock_client = AsyncMock()
        mock_client.generate.return_value = json.dumps([
            {
                "category": "API6_Unrestricted_Access_to_Sensitive_Business_Flows",
                "severity": "high",
                "title": "Mass disbursement without idempotency",
                "description": "The /disburse endpoint allows mass payments without an idempotency key.",
                "recommendation": "Add mandatory idempotency key header.",
                "location": "$.paths['/disburse']",
            }
        ])

        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
security:
  - Bearer: []
components:
  securitySchemes:
    Bearer:
      type: http
      scheme: bearer
servers:
  - url: https://api.example.com/v1
paths:
  /disburse:
    post:
      summary: mass disbursement
"""
        report = await inspector.inspect_api_spec(spec, llm_client=mock_client)
        assert report.llm_augmented is True
        llm_findings = [f for f in report.findings if f.source == "llm"]
        assert len(llm_findings) == 1
        assert llm_findings[0].title == "Mass disbursement without idempotency"

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self, inspector: SecurityInspector):
        mock_client = AsyncMock()
        mock_client.generate.side_effect = RuntimeError("LLM unavailable")

        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
paths:
  /items:
    get:
      summary: list
"""
        report = await inspector.inspect_api_spec(spec, llm_client=mock_client)
        assert report.llm_augmented is False
        assert any("unavailable" in n.lower() for n in report.notes)
        # Rule-based findings still present
        assert len(report.findings) > 0

    @pytest.mark.asyncio
    async def test_llm_none_skips(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
paths:
  /items:
    get:
      summary: list
"""
        report = await inspector.inspect_api_spec(spec, llm_client=None)
        assert report.llm_augmented is False
        assert any("skipped" in n.lower() for n in report.notes)

    @pytest.mark.asyncio
    async def test_llm_deduplicates(self, inspector: SecurityInspector):
        """LLM findings with same title as rule-based findings are dropped."""
        mock_client = AsyncMock()
        mock_client.generate.return_value = json.dumps([
            {
                "category": "API2_Broken_Authentication",
                "severity": "critical",
                "title": "No authentication declared",
                "description": "duplicate of rule-based finding",
                "recommendation": "add auth",
                "location": "",
            },
            {
                "category": "API1_BOLA",
                "severity": "high",
                "title": "Object IDs are sequential",
                "description": "new finding",
                "recommendation": "use UUIDs",
                "location": "$.paths",
            },
        ])

        spec = "openapi: '3.0.3'\ninfo:\n  title: Test\n  version: '1.0'\npaths:\n  /x:\n    get:\n      summary: x"
        report = await inspector.inspect_api_spec(spec, llm_client=mock_client)
        llm_titles = [f.title for f in report.findings if f.source == "llm"]
        assert "No authentication declared" not in llm_titles
        assert "Object IDs are sequential" in llm_titles


# ---------------------------------------------------------------------------
# Report assembly (severity counts, overall risk)
# ---------------------------------------------------------------------------

class TestReportAssembly:
    @pytest.mark.asyncio
    async def test_severity_counts(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
servers:
  - url: http://api.example.com
paths:
  /users/{pan}/data:
    get:
      summary: get by pan
"""
        report = await inspector.inspect_api_spec(spec)
        # Should have: no auth (critical), http url (high), sensitive path (high),
        # no rate limit (medium), missing versioning (low)
        assert report.summary.get("critical", 0) >= 1
        assert report.summary.get("high", 0) >= 1
        assert report.overall_risk == "critical"

    @pytest.mark.asyncio
    async def test_overall_risk_minimal(self, inspector: SecurityInspector):
        """A well-configured spec should produce minimal risk."""
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
  description: "Rate limit: 100 req/min. Returns 429."
security:
  - Bearer: []
components:
  securitySchemes:
    Bearer:
      type: http
      scheme: bearer
servers:
  - url: https://api.example.com/v1
paths:
  /items:
    get:
      summary: list
      responses:
        '429':
          description: rate limited
"""
        report = await inspector.inspect_api_spec(spec)
        assert report.overall_risk == "minimal"
        assert len(report.findings) == 0

    @pytest.mark.asyncio
    async def test_findings_sorted_by_severity(self, inspector: SecurityInspector):
        spec = """
openapi: '3.0.3'
info:
  title: Test
  version: '1.0'
servers:
  - url: http://api.example.com
paths:
  /users/{password}:
    get:
      summary: get
"""
        report = await inspector.inspect_api_spec(spec)
        severities = [f.severity for f in report.findings]
        order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        ordered_values = [order[s] for s in severities]
        assert ordered_values == sorted(ordered_values, reverse=True)


# ---------------------------------------------------------------------------
# Config inspection
# ---------------------------------------------------------------------------

class TestConfigInspection:
    @pytest.mark.asyncio
    async def test_http_base_url_in_config(self, inspector: SecurityInspector):
        config = {"base_url": "http://insecure.example.com", "auth": {"type": "api_key"}}
        report = await inspector.inspect_config(config)
        finding = next(
            (f for f in report.findings if "HTTP base URL" in f.title), None
        )
        assert finding is not None

    @pytest.mark.asyncio
    async def test_no_auth_in_config(self, inspector: SecurityInspector):
        config = {"base_url": "https://secure.example.com"}
        report = await inspector.inspect_config(config)
        finding = next(
            (f for f in report.findings if "No authentication configured" in f.title), None
        )
        assert finding is not None
        assert finding.severity == "critical"

    @pytest.mark.asyncio
    async def test_sensitive_endpoint_in_config(self, inspector: SecurityInspector):
        config = {
            "base_url": "https://secure.example.com",
            "auth": {"type": "bearer"},
            "endpoints": [{"path": "/verify/{aadhaar}", "method": "POST"}],
        }
        report = await inspector.inspect_config(config)
        finding = next(
            (f for f in report.findings if "Sensitive field in endpoint" in f.title), None
        )
        assert finding is not None

    @pytest.mark.asyncio
    async def test_sensitive_field_mapping(self, inspector: SecurityInspector):
        config = {
            "base_url": "https://secure.example.com",
            "auth": {"type": "bearer"},
            "field_mappings": [
                {"source_field": "pan_number", "target_field": "document_id"},
            ],
        }
        report = await inspector.inspect_config(config)
        finding = next(
            (f for f in report.findings if "Sensitive field in mapping" in f.title), None
        )
        assert finding is not None
