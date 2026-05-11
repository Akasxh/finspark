"""LLM-powered integration config generation using OpenRouter (Claude Opus by default).

Takes adapter info + document entities and produces a draft config via
structured JSON generation.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from finspark.core.config import settings
from finspark.services.llm.client import GeminiClient  # alias-compatible with OpenRouterClient

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = """\
You are AdaptConfig's senior integration architect for Indian fintech lending platforms.

Your job: turn a parsed business document + an adapter specification into a runnable
integration config. The config will be deployed by the user's lending platform to call
the real third-party API (CIBIL, eKYC, GST, UPI, Razorpay, Account Aggregator, etc.).

Quality bar:
- The document is the source of truth for endpoint paths, field names, SLAs, and security needs.
- The adapter spec is the source of truth for available endpoints, auth method, and request/response shapes.
- When the document conflicts with the adapter, prefer the adapter (it reflects the actual API contract).
- When a value is missing from both, use industry-standard defaults for Indian fintech (timeouts 5-15s, retries 3 with exponential backoff).
- Never invent endpoint paths not present in either input. Never fabricate field names."""


_GENERATE_PROMPT_TEMPLATE = """\
Generate an integration config from the inputs below.

## Adapter spec
```json
{adapter_info}
```

## Parsed document
```json
{document_content}
```

## User hints
{user_hints}

## Output schema (return JSON exactly matching this shape)

```json
{{
  "base_url": "https://api.example.com/v1",
  "endpoints": [
    {{
      "id": "auth",
      "path": "/oauth/token",
      "method": "POST",
      "description": "Exchange client credentials for access token",
      "depends_on": null,
      "extract": {{"access_token": "$.access_token", "expires_in": "$.expires_in"}},
      "inject": {{}}
    }},
    {{
      "id": "create_payment",
      "path": "/v1/payments",
      "method": "POST",
      "description": "Initiate payment transaction",
      "depends_on": "auth",
      "extract": {{"txn_id": "$.data.id"}},
      "inject": {{"headers.Authorization": "Bearer {{{{auth.access_token}}}}"}}
    }}
  ],
  "auth": {{
    "type": "oauth2",
    "config": {{"token_url": "/oauth/token", "scopes": ["payments:write"]}}
  }},
  "timeout_ms": 10000,
  "retry_count": 3,
  "retry_backoff": "exponential",
  "field_mappings": [
    {{
      "source_field": "pan_number",
      "target_field": "pan",
      "transformation": null,
      "confidence": 0.98
    }}
  ],
  "headers": {{"X-Client-Version": "1.0"}},
  "notes": "OAuth token expires in 3600s; client should cache and refresh proactively."
}}
```

## API chaining (when the API requires multi-step flows)

If the document or adapter describes auth → resource → status patterns:
1. Give EVERY endpoint a SHORT snake_case `id`. This enables chain detection downstream.
2. Set `depends_on` to the upstream endpoint's id (or null for entry points).
3. Use `extract` (JSONPath) to declare which response values downstream endpoints need.
4. Use `inject` (template strings) to wire extracted values into downstream requests.

Template syntax: `{{{{step_id.field_name}}}}` for top-level extracted values, or `{{{{step_id.nested.path}}}}` for nested.

Inject target paths:
- `headers.X-Custom-Header` — set a request header
- `body.parent_txn_id` — set a request body field (nested paths work: `body.nested.field`)
- `path_params.id` — substitute a path placeholder
- `query_params.filter` — set a query string param

Common chain patterns to recognize:
- OAuth2 client credentials: `auth` → `*` (Bearer token injection)
- Payment flow: `tokenize_card` → `authorize` → `capture` → `settle`
- KYC flow: `initiate_session` → `upload_doc` → `verify` → `fetch_result`
- AA framework: `create_consent` → `notify_user` → `fetch_data`

## Field mapping rules

- `source_field` = field name as in the document.
- `target_field` = field name as in the adapter's request schema.
- `confidence` calibration:
  - 0.95-1.00: exact synonym or identical (`pan` ↔ `pan_number`)
  - 0.80-0.94: same semantic meaning, naming variation (`mobile_no` ↔ `phone`)
  - 0.60-0.79: probable match, human review recommended
  - 0.40-0.59: weak match, type-compatible only
  - < 0.40: omit the mapping
- `transformation`: one of `null | parse_number | parse_date | parse_boolean | normalize_phone | validate_email | upper | lower | to_string | format_date`.

## Defaults when unspecified

- timeout_ms: 10000 (10s) — bump to 30000 for credit bureau or report-fetching calls
- retry_count: 3
- retry_backoff: "exponential"
- auth.type: prefer the adapter's declared auth_type unless the document overrides

## Output

Return ONLY the JSON object. No markdown fences. No commentary."""


async def generate_config_llm(
    *,
    adapter_info: dict[str, Any],
    document_content: dict[str, Any],
    user_hint: str = "",
    client: GeminiClient,
) -> dict[str, Any]:
    """Generate an integration config payload using the LLM.

    Routes to the reasoning model (Claude Opus by default) since config generation
    requires architectural judgment, not just extraction.
    """
    prompt = _GENERATE_PROMPT_TEMPLATE.format(
        adapter_info=json.dumps(adapter_info, indent=2),
        document_content=json.dumps(document_content, indent=2),
        user_hints=user_hint or "(none)",
    )

    logger.info("llm_config_generation_start adapter=%s", adapter_info.get("name", "unknown"))

    # Use the reasoning model for config generation when on OpenRouter.
    # GeminiClient doesn't accept a model kwarg, so only pass it when supported.
    extra_kwargs: dict[str, Any] = {}
    if settings.llm_provider == "openrouter" and settings.llm_model_reasoning:
        extra_kwargs["model"] = settings.llm_model_reasoning

    result = await client.generate_json(
        prompt,
        system_instruction=_SYSTEM_INSTRUCTION,
        temperature=0.1,
        max_tokens=8192,
        **extra_kwargs,
    )

    logger.info(
        "llm_config_generation_complete adapter=%s keys=%s",
        adapter_info.get("name", "unknown"),
        list(result.keys()),
    )

    return result
