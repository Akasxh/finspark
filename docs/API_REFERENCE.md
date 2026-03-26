# FinSpark API Reference

> Base URL: `http://localhost:8000`
>
> All tenant-scoped endpoints require the `X-Tenant-ID` header. Default: `default`.

---

## Table of Contents

- [Response Format](#response-format)
- [Error Codes](#error-codes)
- [Health & Metrics](#health--metrics)
- [Documents](#documents)
- [Adapters](#adapters)
- [Configurations](#configurations)
- [Simulations](#simulations)
- [Audit Logs](#audit-logs)
- [Webhooks](#webhooks)

---

## Response Format

All API responses use a standard envelope:

```json
{
  "success": true,
  "data": { ... },
  "message": "",
  "errors": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | `boolean` | Whether the operation succeeded |
| `data` | `T \| null` | Response payload (type varies per endpoint) |
| `message` | `string` | Human-readable status message |
| `errors` | `string[]` | List of error messages (empty on success) |

### Paginated Response

Endpoints returning lists use:

```json
{
  "success": true,
  "data": {
    "items": [ ... ],
    "total": 150,
    "page": 1,
    "page_size": 50,
    "has_next": true
  }
}
```

---

## Error Codes

| HTTP Status | Meaning | Common Causes |
|:-----------:|---------|---------------|
| `400` | Bad Request | Invalid file type, missing required fields, malformed JSON |
| `404` | Not Found | Document/adapter/configuration/simulation/webhook not found, or not accessible by current tenant |
| `422` | Validation Error | Pydantic schema validation failure (FastAPI auto-generated) |
| `429` | Too Many Requests | Rate limit exceeded (100 requests per 60 seconds per tenant). Includes `Retry-After` header |
| `500` | Internal Server Error | Unhandled exception |

### 422 Validation Error Format (FastAPI)

```json
{
  "detail": [
    {
      "loc": ["body", "document_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 429 Rate Limit Error

```json
{
  "detail": "Too many requests. Please retry later."
}
```

Response headers include: `Retry-After: <seconds>`

---

## Health & Metrics

### GET /health

Returns system health status.

**Request:**

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-03-27T10:00:00Z",
  "checks": {
    "database": "ok",
    "ai_enabled": false
  }
}
```

---

### GET /metrics

Returns in-memory API usage metrics.

**Request:**

```http
GET /metrics
```

**Response:**

```json
{
  "total_requests": 1247,
  "requests_per_endpoint": {
    "/api/v1/adapters/": 342,
    "/api/v1/documents/upload": 89,
    "/api/v1/configurations/generate": 56,
    "/api/v1/simulations/run": 23
  },
  "avg_response_time_ms": 45.12,
  "active_tenants": 3
}
```

---

## Documents

### POST /api/v1/documents/upload

Upload and parse a document (BRD, SOW, API spec).

**Headers:**

| Header | Required | Description |
|--------|:--------:|-------------|
| `X-Tenant-ID` | Yes | Tenant identifier |
| `Content-Type` | Yes | `multipart/form-data` |

**Parameters:**

| Name | In | Type | Default | Description |
|------|:--:|------|---------|-------------|
| `file` | body | `UploadFile` | -- | Document file |
| `doc_type` | query | `string` | `"brd"` | One of: `brd`, `sow`, `api_spec`, `other` |

**Allowed file types:** `.docx`, `.pdf`, `.yaml`, `.yml`, `.json`

**Request:**

```http
POST /api/v1/documents/upload?doc_type=brd
Content-Type: multipart/form-data
X-Tenant-ID: tenant-001

file=@credit_bureau_brd.docx
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "filename": "credit_bureau_brd.docx",
    "file_type": "docx",
    "doc_type": "brd",
    "status": "parsed",
    "created_at": "2026-03-27T10:00:00Z"
  },
  "message": "Document parsed"
}
```

**Error (400):**

```json
{
  "detail": "Unsupported file type: .txt. Allowed: {'.docx', '.pdf', '.yaml', '.yml', '.json'}"
}
```

---

### GET /api/v1/documents/

List all documents for the current tenant.

**Request:**

```http
GET /api/v1/documents/
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "filename": "credit_bureau_brd.docx",
      "file_type": "docx",
      "doc_type": "brd",
      "status": "parsed",
      "created_at": "2026-03-27T10:00:00Z"
    }
  ]
}
```

---

### GET /api/v1/documents/{document_id}

Get document details including full parsed results.

**Request:**

```http
GET /api/v1/documents/a1b2c3d4-e5f6-7890-abcd-ef1234567890
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "filename": "credit_bureau_brd.docx",
    "file_type": "docx",
    "doc_type": "brd",
    "status": "parsed",
    "parsed_result": {
      "doc_type": "brd",
      "title": "Credit Bureau Integration BRD",
      "summary": "This document outlines the integration requirements for CIBIL credit bureau...",
      "services_identified": ["CIBIL", "PAN", "Aadhaar"],
      "endpoints": [
        {
          "path": "/v1/credit-score",
          "method": "POST",
          "description": "Fetch credit score",
          "parameters": [],
          "is_mandatory": true
        }
      ],
      "fields": [
        {
          "name": "pan_number",
          "data_type": "string",
          "description": "",
          "is_required": true,
          "sample_value": "",
          "source_section": ""
        },
        {
          "name": "customer_name",
          "data_type": "string",
          "description": "",
          "is_required": true,
          "sample_value": "",
          "source_section": ""
        }
      ],
      "auth_requirements": [
        {
          "auth_type": "api_key",
          "details": {}
        }
      ],
      "security_requirements": ["encryption", "PII mask", "audit log"],
      "sla_requirements": {
        "response_time": "500ms",
        "availability": "99.9%"
      },
      "sections": {
        "overview": "...",
        "integration_requirements": "..."
      },
      "confidence_score": 0.85,
      "raw_entities": ["pan_number", "customer_name", "/v1/credit-score"]
    },
    "created_at": "2026-03-27T10:00:00Z",
    "updated_at": "2026-03-27T10:00:01Z"
  }
}
```

---

## Adapters

### GET /api/v1/adapters/

List all available integration adapters.

**Query Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `category` | `string?` | Filter by category: `bureau`, `kyc`, `gst`, `payment`, `fraud`, `notification` |

**Request:**

```http
GET /api/v1/adapters/?category=bureau
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "adapters": [
      {
        "id": "uuid-adapter-1",
        "name": "CIBIL Credit Bureau",
        "category": "bureau",
        "description": "TransUnion CIBIL credit score and report integration",
        "is_active": true,
        "icon": "credit-card",
        "versions": [
          {
            "id": "uuid-version-1",
            "version": "v1",
            "status": "active",
            "auth_type": "api_key_certificate",
            "base_url": "https://api.cibil.com/v1",
            "endpoints": [
              {
                "path": "/credit-score",
                "method": "POST",
                "description": "Fetch credit score"
              },
              {
                "path": "/credit-report",
                "method": "POST",
                "description": "Fetch detailed credit report"
              }
            ],
            "changelog": null
          },
          {
            "id": "uuid-version-2",
            "version": "v2",
            "status": "active",
            "auth_type": "oauth2",
            "base_url": "https://api.cibil.com/v2",
            "endpoints": [
              {
                "path": "/scores",
                "method": "POST",
                "description": "Fetch credit score (v2)"
              },
              {
                "path": "/reports",
                "method": "POST",
                "description": "Fetch credit report (v2)"
              },
              {
                "path": "/batch/inquiries",
                "method": "POST",
                "description": "Batch credit inquiry"
              },
              {
                "path": "/consent/verify",
                "method": "POST",
                "description": "Verify consent"
              }
            ],
            "changelog": "Added consent verification, batch inquiries, OAuth2 auth"
          }
        ],
        "created_at": "2026-03-27T10:00:00Z"
      }
    ],
    "total": 1,
    "categories": ["bureau", "kyc", "gst", "payment", "fraud", "notification"]
  }
}
```

---

### GET /api/v1/adapters/{adapter_id}

Get a single adapter with all its versions.

**Request:**

```http
GET /api/v1/adapters/uuid-adapter-1
```

**Response (200):** Same structure as a single item from the list endpoint.

**Error (404):**

```json
{
  "detail": "Adapter not found"
}
```

---

### GET /api/v1/adapters/{adapter_id}/match

Find adapters matching a comma-separated list of identified services.

**Query Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `services` | `string` | Comma-separated service names (e.g., `CIBIL,KYC,GST`) |

**Request:**

```http
GET /api/v1/adapters/any-id/match?services=CIBIL,KYC,GST
```

**Response (200):**

```json
{
  "success": true,
  "data": [
    "CIBIL Credit Bureau",
    "Aadhaar eKYC Provider",
    "GST Verification Service"
  ]
}
```

---

## Configurations

### GET /api/v1/configurations/templates

List pre-built configuration templates for common integration patterns.

**Request:**

```http
GET /api/v1/configurations/templates
```

**Response (200):**

```json
{
  "success": true,
  "data": [
    {
      "name": "Credit Bureau Basic",
      "description": "Basic credit bureau pull with PAN and consent fields",
      "adapter_category": "bureau",
      "default_config": {
        "base_url": "https://api.bureau-provider.in/v1",
        "auth": {
          "type": "api_key",
          "header": "X-API-Key"
        },
        "endpoints": [
          {
            "path": "/credit-pull",
            "method": "POST"
          }
        ],
        "field_mappings": [
          {
            "source_field": "pan_number",
            "target_field": "pan",
            "transformation": "upper"
          },
          {
            "source_field": "full_name",
            "target_field": "name"
          }
        ]
      }
    },
    {
      "name": "KYC Standard",
      "description": "Standard KYC verification with Aadhaar and PAN",
      "adapter_category": "kyc",
      "default_config": { "..." : "..." }
    },
    {
      "name": "Payment Gateway",
      "description": "Payment gateway integration with order and amount fields",
      "adapter_category": "payment",
      "default_config": { "..." : "..." }
    },
    {
      "name": "GST Verification",
      "description": "GST number verification and return filing lookup",
      "adapter_category": "gst",
      "default_config": { "..." : "..." }
    }
  ]
}
```

---

### POST /api/v1/configurations/generate

Generate an integration configuration from a parsed document and adapter version.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `document_id` | `string` | Yes | UUID of a parsed document |
| `adapter_version_id` | `string` | Yes | UUID of the adapter version |
| `name` | `string` | Yes | Name for the configuration |
| `auto_map` | `boolean` | No | Use AI-assisted field mapping (default: `true`) |

**Request:**

```http
POST /api/v1/configurations/generate
Content-Type: application/json
X-Tenant-ID: tenant-001

{
  "document_id": "doc-uuid-123",
  "adapter_version_id": "av-uuid-456",
  "name": "CIBIL Integration - Production"
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "config-uuid-789",
    "name": "CIBIL Integration - Production",
    "adapter_version_id": "av-uuid-456",
    "document_id": "doc-uuid-123",
    "status": "configured",
    "version": 1,
    "field_mappings": [
      {
        "source_field": "pan_number",
        "target_field": "pan_number",
        "transformation": null,
        "confidence": 1.0,
        "is_confirmed": true
      },
      {
        "source_field": "customer_name",
        "target_field": "full_name",
        "transformation": null,
        "confidence": 0.85,
        "is_confirmed": false
      },
      {
        "source_field": "date_of_birth",
        "target_field": "dob",
        "transformation": null,
        "confidence": 1.0,
        "is_confirmed": true
      },
      {
        "source_field": "mobile",
        "target_field": "mobile_number",
        "transformation": "normalize_phone",
        "confidence": 0.92,
        "is_confirmed": true
      }
    ],
    "created_at": "2026-03-27T10:05:00Z",
    "updated_at": "2026-03-27T10:05:00Z"
  },
  "message": "Configuration generated successfully"
}
```

**Error (404):**

```json
{
  "detail": "Parsed document not found"
}
```

---

### GET /api/v1/configurations/

List all configurations for the current tenant.

**Request:**

```http
GET /api/v1/configurations/
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": [
    {
      "id": "config-uuid-789",
      "name": "CIBIL Integration - Production",
      "adapter_version_id": "av-uuid-456",
      "document_id": "doc-uuid-123",
      "status": "configured",
      "version": 1,
      "field_mappings": [ ... ],
      "created_at": "2026-03-27T10:05:00Z",
      "updated_at": "2026-03-27T10:05:00Z"
    }
  ]
}
```

---

### GET /api/v1/configurations/{config_id}

Get configuration details.

**Request:**

```http
GET /api/v1/configurations/config-uuid-789
X-Tenant-ID: tenant-001
```

**Response:** Same structure as a single item from the list endpoint.

---

### POST /api/v1/configurations/{config_id}/validate

Validate a configuration for completeness and correctness.

**Request:**

```http
POST /api/v1/configurations/config-uuid-789/validate
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "is_valid": true,
    "errors": [],
    "warnings": [
      "2 mappings have low confidence"
    ],
    "coverage_score": 0.88,
    "missing_required_fields": [],
    "unmapped_source_fields": ["internal_ref"]
  }
}
```

Validation checks:
- `base_url` is present
- `auth.type` is configured
- At least one endpoint exists
- Field mapping coverage and confidence scores

---

### GET /api/v1/configurations/{config_a_id}/diff/{config_b_id}

Compare two configurations and show differences.

**Request:**

```http
GET /api/v1/configurations/config-uuid-1/diff/config-uuid-2
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "config_a_id": "config-uuid-1",
    "config_b_id": "config-uuid-2",
    "total_changes": 5,
    "breaking_changes": 2,
    "diffs": [
      {
        "path": "base_url",
        "change_type": "modified",
        "old_value": "https://api.cibil.com/v1",
        "new_value": "https://api.cibil.com/v2",
        "is_breaking": true
      },
      {
        "path": "auth.type",
        "change_type": "modified",
        "old_value": "api_key_certificate",
        "new_value": "oauth2",
        "is_breaking": true
      },
      {
        "path": "endpoints[3]",
        "change_type": "added",
        "old_value": null,
        "new_value": {
          "path": "/consent/verify",
          "method": "POST",
          "description": "Verify consent",
          "enabled": true
        },
        "is_breaking": true
      },
      {
        "path": "field_mappings[2].target_field",
        "change_type": "modified",
        "old_value": "date_of_birth",
        "new_value": "dob",
        "is_breaking": false
      }
    ]
  }
}
```

Breaking change paths: `auth.type`, `base_url`, `version`, `endpoints`

---

### GET /api/v1/configurations/{config_id}/export

Export a configuration as a downloadable JSON or YAML file.

**Query Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `format` | `string` | `"json"` | Export format: `json` or `yaml` |

**Request:**

```http
GET /api/v1/configurations/config-uuid-789/export?format=yaml
X-Tenant-ID: tenant-001
```

**Response:** Binary download with `Content-Disposition: attachment` header.

```yaml
id: config-uuid-789
name: CIBIL Integration - Production
version: 1
status: configured
config:
  adapter_name: uuid-adapter-1
  version: v2
  base_url: https://api.cibil.com/v2
  auth:
    type: oauth2
    credentials: {}
  endpoints:
    - path: /scores
      method: POST
      description: Fetch credit score (v2)
      enabled: true
  field_mappings:
    - source_field: pan_number
      target_field: pan_number
      confidence: 1.0
  retry_policy:
    max_retries: 3
    backoff_factor: 2
    retry_on_status: [429, 500, 502, 503]
  timeout_ms: 30000
```

---

## Simulations

### POST /api/v1/simulations/run

Run a mock simulation against a configuration.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `configuration_id` | `string` | Yes | UUID of the configuration to test |
| `test_type` | `string` | No | `full` (default), `smoke`, `schema_only`, `parallel_version` |
| `mock_responses` | `object?` | No | Custom mock response overrides |

**Request:**

```http
POST /api/v1/simulations/run
Content-Type: application/json
X-Tenant-ID: tenant-001

{
  "configuration_id": "config-uuid-789",
  "test_type": "full"
}
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "sim-uuid-001",
    "configuration_id": "config-uuid-789",
    "status": "passed",
    "test_type": "full",
    "total_tests": 7,
    "passed_tests": 7,
    "failed_tests": 0,
    "duration_ms": 12,
    "steps": [
      {
        "step_name": "config_structure_validation",
        "status": "passed",
        "request_payload": {
          "required_keys": ["adapter_name", "version", "base_url", "auth", "endpoints", "field_mappings"]
        },
        "expected_response": { "missing": [] },
        "actual_response": { "missing": [] },
        "duration_ms": 1,
        "confidence_score": 1.0,
        "error_message": null,
        "assertions": []
      },
      {
        "step_name": "field_mapping_validation",
        "status": "passed",
        "request_payload": { "total_fields": 8 },
        "expected_response": { "coverage": ">= 0.7" },
        "actual_response": {
          "coverage": 0.88,
          "mapped": 7,
          "unmapped": 1,
          "low_confidence": 0
        },
        "duration_ms": 1,
        "confidence_score": 0.88,
        "error_message": null,
        "assertions": []
      },
      {
        "step_name": "endpoint_test_/scores",
        "status": "passed",
        "request_payload": {
          "pan_number": "ABCDE1234F",
          "full_name": "Rajesh Kumar Sharma",
          "date_of_birth": "1990-05-15"
        },
        "expected_response": { "status": "success" },
        "actual_response": {
          "status": "success",
          "code": 200,
          "data": {
            "reference_id": "REF-2024-001234",
            "message": "Mock response for /scores",
            "timestamp": "2024-03-26T10:00:00Z"
          }
        },
        "duration_ms": 1,
        "confidence_score": 0.9,
        "error_message": null,
        "assertions": []
      },
      {
        "step_name": "auth_config_validation",
        "status": "passed",
        "request_payload": { "auth_config": { "type": "oauth2" } },
        "expected_response": { "has_auth_type": true },
        "actual_response": { "has_auth_type": true, "auth_type": "oauth2" },
        "duration_ms": 1,
        "confidence_score": 1.0,
        "error_message": null,
        "assertions": []
      },
      {
        "step_name": "hooks_validation",
        "status": "passed",
        "request_payload": { "total_hooks": 4 },
        "expected_response": { "invalid_hooks": 0 },
        "actual_response": {
          "total_hooks": 4,
          "invalid_hooks": 0,
          "hook_types": ["pre_request", "post_response"]
        },
        "duration_ms": 1,
        "confidence_score": 1.0,
        "error_message": null,
        "assertions": []
      },
      {
        "step_name": "error_handling_validation",
        "status": "passed",
        "request_payload": {},
        "expected_response": { "has_retry": true, "has_timeout": true },
        "actual_response": {
          "has_retry": true,
          "has_timeout": true,
          "has_error_hook": false
        },
        "duration_ms": 1,
        "confidence_score": 0.67,
        "error_message": null,
        "assertions": []
      },
      {
        "step_name": "retry_logic_validation",
        "status": "passed",
        "request_payload": {
          "retry_policy": {
            "max_retries": 3,
            "backoff_factor": 2,
            "retry_on_status": [429, 500, 502, 503]
          }
        },
        "expected_response": { "valid": true },
        "actual_response": {
          "valid": true,
          "max_retries": 3,
          "has_backoff": true,
          "has_status_codes": true
        },
        "duration_ms": 1,
        "confidence_score": 1.0,
        "error_message": null,
        "assertions": []
      }
    ],
    "created_at": "2026-03-27T10:10:00Z"
  },
  "message": "Simulation passed: 7/7 tests passed"
}
```

### Simulation Test Steps (full test_type)

| Step | Name | Passes When |
|:----:|------|------------|
| 1 | `config_structure_validation` | All required keys present: `adapter_name`, `version`, `base_url`, `auth`, `endpoints`, `field_mappings` |
| 2 | `field_mapping_validation` | Coverage >= 70% and low-confidence mappings <= 30% |
| 3..N | `endpoint_test_{path}` | Mock response contains `status` field |
| N+1 | `auth_config_validation` | Auth type is non-empty |
| N+2 | `hooks_validation` | All hooks have valid types: `pre_request`, `post_response`, `on_error`, `on_timeout` |
| N+3 | `error_handling_validation` | At least 2 of 3: retry policy, timeout, error hook |
| N+4 | `retry_logic_validation` | `max_retries` 1-5 and `backoff_factor` present |

---

### GET /api/v1/simulations/{simulation_id}

Get simulation results.

**Request:**

```http
GET /api/v1/simulations/sim-uuid-001
X-Tenant-ID: tenant-001
```

**Response:** Same structure as the `run` response.

---

### GET /api/v1/simulations/{simulation_id}/stream

Stream simulation results as Server-Sent Events (SSE).

**Request:**

```http
GET /api/v1/simulations/{config_id}/stream
X-Tenant-ID: tenant-001
Accept: text/event-stream
```

**Response (SSE stream):**

```
event: step
data: {"step_name": "config_structure_validation", "status": "passed", "duration_ms": 1, "confidence_score": 1.0}

event: step
data: {"step_name": "field_mapping_validation", "status": "passed", "duration_ms": 1, "confidence_score": 0.88}

event: step
data: {"step_name": "endpoint_test_/scores", "status": "passed", "duration_ms": 1, "confidence_score": 0.9}

event: done
data: {"total_steps": 7}
```

---

## Audit Logs

### GET /api/v1/audit/

Query audit logs for the current tenant. Results are paginated.

**Query Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `resource_type` | `string?` | -- | Filter: `configuration`, `adapter`, `simulation`, `document` |
| `resource_id` | `string?` | -- | Filter by specific resource UUID |
| `action` | `string?` | -- | Filter: `upload_document`, `generate_config`, `run_simulation`, `deploy`, `rollback` |
| `page` | `int` | `1` | Page number |
| `page_size` | `int` | `50` | Items per page |

**Request:**

```http
GET /api/v1/audit/?resource_type=configuration&page=1&page_size=20
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "audit-uuid-001",
        "tenant_id": "tenant-001",
        "actor": "Default Tenant",
        "action": "generate_config",
        "resource_type": "configuration",
        "resource_id": "config-uuid-789",
        "details": {
          "adapter_version": "v2",
          "document": "credit_bureau_brd.docx"
        },
        "created_at": "2026-03-27T10:05:00Z"
      },
      {
        "id": "audit-uuid-002",
        "tenant_id": "tenant-001",
        "actor": "Default Tenant",
        "action": "run_simulation",
        "resource_type": "simulation",
        "resource_id": "sim-uuid-001",
        "details": {
          "config_id": "config-uuid-789",
          "status": "passed",
          "passed": 7,
          "failed": 0
        },
        "created_at": "2026-03-27T10:10:00Z"
      }
    ],
    "total": 2,
    "page": 1,
    "page_size": 20,
    "has_next": false
  }
}
```

---

## Webhooks

### POST /api/v1/webhooks/

Register a new webhook endpoint for receiving integration events.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `url` | `string (HttpUrl)` | Yes | Webhook endpoint URL |
| `secret` | `string` | Yes | Shared secret for HMAC verification (stored Fernet-encrypted) |
| `events` | `string[]` | No | Event types to subscribe to (default: `[]` = all) |
| `is_active` | `boolean` | No | Enable/disable (default: `true`) |

**Request:**

```http
POST /api/v1/webhooks/
Content-Type: application/json
X-Tenant-ID: tenant-001

{
  "url": "https://hooks.example.com/finspark",
  "secret": "whsec_abc123def456",
  "events": ["configuration.deployed", "simulation.completed"],
  "is_active": true
}
```

**Response (201):**

```json
{
  "success": true,
  "data": {
    "id": "wh-uuid-001",
    "tenant_id": "tenant-001",
    "url": "https://hooks.example.com/finspark",
    "events": ["configuration.deployed", "simulation.completed"],
    "is_active": true,
    "created_at": "2026-03-27T10:15:00Z"
  },
  "message": "Webhook registered"
}
```

---

### GET /api/v1/webhooks/

List all webhooks for the current tenant.

**Request:**

```http
GET /api/v1/webhooks/
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": [
    {
      "id": "wh-uuid-001",
      "tenant_id": "tenant-001",
      "url": "https://hooks.example.com/finspark",
      "events": ["configuration.deployed", "simulation.completed"],
      "is_active": true,
      "created_at": "2026-03-27T10:15:00Z"
    }
  ]
}
```

---

### DELETE /api/v1/webhooks/{webhook_id}

Delete a webhook.

**Request:**

```http
DELETE /api/v1/webhooks/wh-uuid-001
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": null,
  "message": "Webhook deleted"
}
```

---

### POST /api/v1/webhooks/{webhook_id}/test

Send a test event to a webhook endpoint.

**Request:**

```http
POST /api/v1/webhooks/wh-uuid-001/test
X-Tenant-ID: tenant-001
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "delivery-uuid-001",
    "webhook_id": "wh-uuid-001",
    "event_type": "webhook.test",
    "payload": {
      "event": "webhook.test",
      "timestamp": "2026-03-27T10:20:00Z",
      "webhook_id": "wh-uuid-001",
      "tenant_id": "tenant-001"
    },
    "status": "delivered",
    "response_code": 200,
    "attempts": 1,
    "created_at": "2026-03-27T10:20:00Z"
  },
  "message": "Test event sent"
}
```

---

## Request Headers

| Header | Required | Default | Description |
|--------|:--------:|---------|-------------|
| `X-Tenant-ID` | For tenant-scoped endpoints | `default` | Tenant identifier for multi-tenant isolation |
| `X-Tenant-Name` | No | `Default Tenant` | Human-readable tenant name |
| `X-Tenant-Role` | No | `admin` | Role: `admin`, `configurator`, `viewer` |
| `Content-Type` | For POST/PUT | `application/json` | Use `multipart/form-data` for file uploads |

## Response Headers

| Header | Description |
|--------|-------------|
| `X-Tenant-ID` | Echo of the tenant ID used for the request |
| `X-Response-Time` | Request processing duration (e.g., `12.5ms`) |
| `Retry-After` | Seconds to wait before retrying (only on 429) |

---

## Interactive Documentation

- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`
- **OpenAPI JSON:** `GET /openapi.json`
