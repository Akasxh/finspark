"""API security inspector with rule-based + LLM semantic analysis.

Covers OWASP API Security Top 10 (2023):
  API1  Broken Object Level Authorization (BOLA)
  API2  Broken Authentication
  API3  Broken Object Property Level Authorization
  API4  Unrestricted Resource Consumption
  API5  Broken Function Level Authorization
  API6  Unrestricted Access to Sensitive Business Flows
  API7  Server Side Request Forgery
  API8  Security Misconfiguration
  API9  Improper Inventory Management
  API10 Unsafe Consumption of APIs
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import yaml

from finspark.schemas.security import SecurityFinding, SecurityReport

logger = logging.getLogger(__name__)

# Sensitive field names that should never appear in URL paths
_SENSITIVE_PATH_PATTERNS = re.compile(
    r"(pan|aadhaar|password|token|secret|ssn)", re.IGNORECASE
)

# Hardcoded API key patterns in example values
_HARDCODED_KEY_PATTERN = re.compile(
    r"(sk[-_]|pk[-_]|api[-_]?key|bearer\s+|token\s*[:=])", re.IGNORECASE
)

_OLD_TLS_VERSIONS = {"tlsv1.0", "tlsv1.1", "tls1.0", "tls1.1", "tls 1.0", "tls 1.1"}

_VERSIONED_PATH = re.compile(r"/v\d+([/.]|$)")


class SecurityInspector:
    """Hybrid rule-based + LLM security inspector for API specs and configs."""

    INSPECTOR_VERSION = "1.0"

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def inspect_api_spec(
        self,
        spec_text: str,
        llm_client: Any | None = None,
    ) -> SecurityReport:
        """Analyze a raw OpenAPI/AsyncAPI YAML or JSON spec."""
        parsed = self._parse_spec(spec_text)
        findings = self._run_rule_checks(parsed, spec_text)

        llm_augmented = False
        notes: list[str] = []

        if llm_client is not None:
            try:
                llm_findings = await self._run_llm_analysis(
                    spec_text, findings, llm_client
                )
                findings.extend(llm_findings)
                llm_augmented = True
            except Exception:
                logger.warning("LLM analysis failed; returning rule-based findings only", exc_info=True)
                notes.append("LLM analysis was unavailable; report contains rule-based findings only.")
        else:
            notes.append("LLM analysis skipped (no client provided); report contains rule-based findings only.")

        return self._build_report(findings, llm_augmented=llm_augmented, notes=notes)

    async def inspect_config(
        self,
        config: dict[str, Any],
        llm_client: Any | None = None,
    ) -> SecurityReport:
        """Analyze an integration config dict."""
        config_text = json.dumps(config, indent=2, default=str)
        # Treat config as a pseudo-spec for rule checking
        findings = self._run_config_checks(config)

        llm_augmented = False
        notes: list[str] = []

        if llm_client is not None:
            try:
                llm_findings = await self._run_llm_analysis(
                    config_text, findings, llm_client
                )
                findings.extend(llm_findings)
                llm_augmented = True
            except Exception:
                logger.warning("LLM analysis failed for config inspection", exc_info=True)
                notes.append("LLM analysis was unavailable; report contains rule-based findings only.")
        else:
            notes.append("LLM analysis skipped (no client provided); report contains rule-based findings only.")

        return self._build_report(findings, llm_augmented=llm_augmented, notes=notes)

    # ------------------------------------------------------------------
    # Spec parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_spec(spec_text: str) -> dict[str, Any]:
        """Parse YAML or JSON spec text into a dict."""
        text = spec_text.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        try:
            return yaml.safe_load(text) or {}
        except yaml.YAMLError:
            return {}

    # ------------------------------------------------------------------
    # Rule-based checks on OpenAPI/AsyncAPI specs
    # ------------------------------------------------------------------

    def _run_rule_checks(
        self, spec: dict[str, Any], raw_text: str
    ) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        findings.extend(self._check_no_auth(spec))
        findings.extend(self._check_http_base_url(spec))
        findings.extend(self._check_credentials_in_url(spec))
        findings.extend(self._check_sensitive_path_params(spec))
        findings.extend(self._check_wildcard_cors(spec, raw_text))
        findings.extend(self._check_no_rate_limiting(spec, raw_text))
        findings.extend(self._check_plaintext_password(spec))
        findings.extend(self._check_old_tls(raw_text))
        findings.extend(self._check_hardcoded_api_key(spec))
        findings.extend(self._check_missing_versioning(spec))
        return findings

    def _check_no_auth(self, spec: dict[str, Any]) -> list[SecurityFinding]:
        """API2: No authentication scheme declared."""
        security = spec.get("security")
        components = spec.get("components", {})
        security_schemes = components.get("securitySchemes", {})

        if not security and not security_schemes:
            return [
                SecurityFinding(
                    category="API2_Broken_Authentication",
                    severity="critical",
                    title="No authentication declared",
                    description=(
                        "The API spec defines no security schemes and no "
                        "global security requirements. All endpoints are "
                        "effectively public."
                    ),
                    recommendation=(
                        "Add a securitySchemes section under components and "
                        "apply a global security requirement (e.g. OAuth2, "
                        "API key, or bearer token)."
                    ),
                    location="$.security / $.components.securitySchemes",
                )
            ]
        return []

    def _check_http_base_url(self, spec: dict[str, Any]) -> list[SecurityFinding]:
        """API8: Base URL uses HTTP instead of HTTPS."""
        findings: list[SecurityFinding] = []
        servers = spec.get("servers", [])
        for i, server in enumerate(servers):
            url = server.get("url", "")
            if url.lower().startswith("http://"):
                findings.append(
                    SecurityFinding(
                        category="API8_Security_Misconfiguration",
                        severity="high",
                        title="HTTP base URL (no TLS)",
                        description=f"Server URL '{url}' uses plaintext HTTP. All API traffic is unencrypted.",
                        recommendation="Use HTTPS for all server URLs to encrypt traffic in transit.",
                        location=f"$.servers[{i}].url",
                    )
                )
        return findings

    def _check_credentials_in_url(self, spec: dict[str, Any]) -> list[SecurityFinding]:
        """API2: Auth credentials passed via URL query string."""
        findings: list[SecurityFinding] = []
        schemes = spec.get("components", {}).get("securitySchemes", {})
        for name, scheme in schemes.items():
            if scheme.get("type") == "apiKey" and scheme.get("in") == "query":
                findings.append(
                    SecurityFinding(
                        category="API2_Broken_Authentication",
                        severity="high",
                        title="Auth credentials in query string",
                        description=(
                            f"Security scheme '{name}' sends the API key as a "
                            "query parameter. Query strings are logged by proxies, "
                            "CDNs, and browser history."
                        ),
                        recommendation="Move the API key to a request header instead of the query string.",
                        location=f"$.components.securitySchemes.{name}",
                    )
                )
        return findings

    def _check_sensitive_path_params(self, spec: dict[str, Any]) -> list[SecurityFinding]:
        """API3: Sensitive fields exposed in URL path segments."""
        findings: list[SecurityFinding] = []
        paths = spec.get("paths", {})
        for path in paths:
            matches = _SENSITIVE_PATH_PATTERNS.findall(path)
            if matches:
                findings.append(
                    SecurityFinding(
                        category="API3_Broken_Object_Property_Level_Authorization",
                        severity="high",
                        title="Sensitive field in URL path",
                        description=(
                            f"Path '{path}' contains sensitive identifier(s): "
                            f"{', '.join(matches)}. URL paths are logged everywhere."
                        ),
                        recommendation=(
                            "Move sensitive identifiers to the request body or "
                            "use opaque reference IDs in paths instead."
                        ),
                        location=f"$.paths['{path}']",
                    )
                )
        return findings

    def _check_wildcard_cors(
        self, spec: dict[str, Any], raw_text: str
    ) -> list[SecurityFinding]:
        """API8: Wildcard CORS origin."""
        text_lower = raw_text.lower()
        if "access-control-allow-origin" in text_lower and "*" in raw_text:
            return [
                SecurityFinding(
                    category="API8_Security_Misconfiguration",
                    severity="medium",
                    title="Wildcard CORS origin",
                    description=(
                        "The spec declares or references 'Access-Control-Allow-Origin: *'. "
                        "This allows any website to make authenticated cross-origin requests."
                    ),
                    recommendation=(
                        "Restrict CORS to specific trusted origins instead of using a wildcard."
                    ),
                    location="Access-Control-Allow-Origin header",
                )
            ]
        return []

    def _check_no_rate_limiting(
        self, spec: dict[str, Any], raw_text: str
    ) -> list[SecurityFinding]:
        """API4: No rate limiting / throttling mentioned."""
        indicators = ["rate.limit", "throttl", "x-ratelimit", "429", "too many requests"]
        text_lower = raw_text.lower()
        if not any(ind in text_lower for ind in indicators):
            return [
                SecurityFinding(
                    category="API4_Unrestricted_Resource_Consumption",
                    severity="medium",
                    title="No rate limiting mentioned",
                    description=(
                        "The API spec does not mention rate limiting, throttling, "
                        "or HTTP 429 responses. Without rate limits, the API is "
                        "vulnerable to abuse and denial-of-service."
                    ),
                    recommendation=(
                        "Document rate limits in the spec, return 429 status codes, "
                        "and include X-RateLimit-* response headers."
                    ),
                    location="(global)",
                )
            ]
        return []

    def _check_plaintext_password(self, spec: dict[str, Any]) -> list[SecurityFinding]:
        """API2: Password fields without format: password."""
        findings: list[SecurityFinding] = []
        self._walk_schemas_for_password(
            spec.get("components", {}).get("schemas", {}),
            findings,
            "$.components.schemas",
        )
        return findings

    def _walk_schemas_for_password(
        self,
        schemas: dict[str, Any],
        findings: list[SecurityFinding],
        path_prefix: str,
    ) -> None:
        for schema_name, schema_def in schemas.items():
            props = schema_def.get("properties", {})
            for prop_name, prop_def in props.items():
                if "password" in prop_name.lower() and prop_def.get("format") != "password":
                    findings.append(
                        SecurityFinding(
                            category="API2_Broken_Authentication",
                            severity="medium",
                            title="Plaintext password field",
                            description=(
                                f"Field '{prop_name}' in schema '{schema_name}' "
                                "looks like a password but does not use "
                                "'format: password'. UIs may render it in cleartext."
                            ),
                            recommendation=(
                                f"Add 'format: password' to the '{prop_name}' "
                                "field definition so clients mask input."
                            ),
                            location=f"{path_prefix}.{schema_name}.properties.{prop_name}",
                        )
                    )

    def _check_old_tls(self, raw_text: str) -> list[SecurityFinding]:
        """API8: Old TLS version references."""
        text_lower = raw_text.lower()
        for version in _OLD_TLS_VERSIONS:
            if version in text_lower:
                return [
                    SecurityFinding(
                        category="API8_Security_Misconfiguration",
                        severity="high",
                        title="Deprecated TLS version referenced",
                        description=(
                            f"The spec references '{version.upper()}', which is "
                            "deprecated and vulnerable to known attacks (POODLE, BEAST)."
                        ),
                        recommendation="Require TLS 1.2 or higher. Remove support for TLS 1.0 and 1.1.",
                        location="(TLS configuration)",
                    )
                ]
        return []

    def _check_hardcoded_api_key(self, spec: dict[str, Any]) -> list[SecurityFinding]:
        """API2: Hardcoded API keys in example values."""
        findings: list[SecurityFinding] = []
        schemas = spec.get("components", {}).get("schemas", {})
        for schema_name, schema_def in schemas.items():
            props = schema_def.get("properties", {})
            for prop_name, prop_def in props.items():
                example = prop_def.get("example", "")
                if isinstance(example, str) and _HARDCODED_KEY_PATTERN.search(example):
                    findings.append(
                        SecurityFinding(
                            category="API2_Broken_Authentication",
                            severity="high",
                            title="Hardcoded API key in schema example",
                            description=(
                                f"Schema '{schema_name}.{prop_name}' has an example "
                                f"value that looks like a real credential: '{example[:30]}...'"
                            ),
                            recommendation=(
                                "Replace example values with clearly fake placeholders "
                                "(e.g. 'YOUR_API_KEY_HERE') that cannot be mistaken for real secrets."
                            ),
                            location=f"$.components.schemas.{schema_name}.properties.{prop_name}.example",
                        )
                    )
        return findings

    def _check_missing_versioning(self, spec: dict[str, Any]) -> list[SecurityFinding]:
        """API9: No API versioning in server URLs or paths."""
        # Check servers
        servers = spec.get("servers", [])
        for server in servers:
            url = server.get("url", "")
            if _VERSIONED_PATH.search(url):
                return []

        # Check paths
        paths = spec.get("paths", {})
        for path in paths:
            if _VERSIONED_PATH.search(path):
                return []

        if servers or paths:
            return [
                SecurityFinding(
                    category="API9_Improper_Inventory_Management",
                    severity="low",
                    title="Missing API versioning in paths",
                    description=(
                        "No version prefix (e.g. /v1/, /v2/) found in server URLs "
                        "or path definitions. Without versioning, breaking changes "
                        "cannot be rolled out safely."
                    ),
                    recommendation=(
                        "Add version prefixes to your API paths (e.g. /v1/resource) "
                        "or use URL-based versioning in server URLs."
                    ),
                    location="$.servers / $.paths",
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Rule-based checks on integration configs
    # ------------------------------------------------------------------

    def _run_config_checks(self, config: dict[str, Any]) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        # Check base_url for HTTP
        base_url = config.get("base_url", "")
        if isinstance(base_url, str) and base_url.lower().startswith("http://"):
            findings.append(
                SecurityFinding(
                    category="API8_Security_Misconfiguration",
                    severity="high",
                    title="HTTP base URL (no TLS)",
                    description=f"Config base_url '{base_url}' uses plaintext HTTP.",
                    recommendation="Use HTTPS for all base URLs.",
                    location="$.base_url",
                )
            )

        # Check auth
        auth = config.get("auth", {})
        if not auth:
            findings.append(
                SecurityFinding(
                    category="API2_Broken_Authentication",
                    severity="critical",
                    title="No authentication configured",
                    description="The integration config has no auth section.",
                    recommendation="Configure authentication (API key, OAuth2, bearer token).",
                    location="$.auth",
                )
            )

        # Check endpoints for sensitive path params
        endpoints = config.get("endpoints", [])
        for i, ep in enumerate(endpoints):
            path = ep.get("path", "")
            matches = _SENSITIVE_PATH_PATTERNS.findall(path)
            if matches:
                findings.append(
                    SecurityFinding(
                        category="API3_Broken_Object_Property_Level_Authorization",
                        severity="high",
                        title="Sensitive field in endpoint path",
                        description=(
                            f"Endpoint '{path}' contains sensitive identifier(s): "
                            f"{', '.join(matches)}."
                        ),
                        recommendation="Move sensitive identifiers to the request body.",
                        location=f"$.endpoints[{i}].path",
                    )
                )

        # Check field_mappings for sensitive fields
        mappings = config.get("field_mappings", [])
        for i, fm in enumerate(mappings):
            for field_key in ("source_field", "target_field"):
                field_val = fm.get(field_key, "")
                if isinstance(field_val, str) and _SENSITIVE_PATH_PATTERNS.search(field_val):
                    findings.append(
                        SecurityFinding(
                            category="API3_Broken_Object_Property_Level_Authorization",
                            severity="medium",
                            title="Sensitive field in mapping",
                            description=(
                                f"Field mapping {field_key}='{field_val}' references "
                                "a sensitive identifier. Ensure it is encrypted in transit and at rest."
                            ),
                            recommendation="Apply encryption, masking, or tokenization to sensitive fields.",
                            location=f"$.field_mappings[{i}].{field_key}",
                        )
                    )

        return findings

    # ------------------------------------------------------------------
    # LLM semantic analysis
    # ------------------------------------------------------------------

    async def _run_llm_analysis(
        self,
        spec_text: str,
        existing_findings: list[SecurityFinding],
        llm_client: Any,
    ) -> list[SecurityFinding]:
        """Ask the LLM for additional semantic security findings."""
        existing_titles = [f.title for f in existing_findings]
        existing_summary = "\n".join(
            f"- [{f.severity.upper()}] {f.title}: {f.description[:120]}"
            for f in existing_findings[:15]
        )

        prompt = f"""You are an API security auditor. Analyze this API specification for security risks
beyond what rule-based checks have already found.

ALREADY FOUND (do NOT duplicate these):
{existing_summary or "(none)"}

API SPECIFICATION:
{spec_text[:8000]}

Return a JSON array of additional findings. Each finding must have:
- "category": one of API1_BOLA, API2_Broken_Authentication, API3_Broken_Object_Property_Level_Authorization,
  API4_Unrestricted_Resource_Consumption, API5_Broken_Function_Level_Authorization,
  API6_Unrestricted_Access_to_Sensitive_Business_Flows, API7_SSRF,
  API8_Security_Misconfiguration, API9_Improper_Inventory_Management,
  API10_Unsafe_Consumption_of_APIs
- "severity": critical, high, medium, low, or info
- "title": short title
- "description": what is wrong
- "recommendation": how to fix it
- "location": where in the spec the issue is

Only return findings NOT already covered above. Focus on business logic flaws,
authorization gaps, data exposure risks, and missing security controls.
Return [] if no additional issues found. Return ONLY the JSON array."""

        raw = await llm_client.generate(
            prompt,
            system_instruction="You are a senior API security auditor. Return only valid JSON.",
            temperature=0.1,
            max_tokens=2048,
            response_json=True,
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON response for security analysis")
            return []

        if isinstance(parsed, dict) and "findings" in parsed:
            parsed = parsed["findings"]
        if not isinstance(parsed, list):
            return []

        llm_findings: list[SecurityFinding] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            if title in existing_titles:
                continue
            try:
                llm_findings.append(
                    SecurityFinding(
                        category=item.get("category", "API8_Security_Misconfiguration"),
                        severity=item.get("severity", "medium"),
                        title=title,
                        description=item.get("description", ""),
                        recommendation=item.get("recommendation", ""),
                        location=item.get("location", ""),
                        source="llm",
                    )
                )
            except Exception:
                continue

        return llm_findings

    # ------------------------------------------------------------------
    # Report assembly
    # ------------------------------------------------------------------

    @classmethod
    def _build_report(
        cls,
        findings: list[SecurityFinding],
        *,
        llm_augmented: bool = False,
        notes: list[str] | None = None,
    ) -> SecurityReport:
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        findings.sort(key=lambda f: severity_order.get(f.severity, 0), reverse=True)

        summary: dict[str, int] = {}
        for f in findings:
            summary[f.severity] = summary.get(f.severity, 0) + 1

        overall_risk = cls._compute_overall_risk(summary)

        return SecurityReport(
            findings=findings,
            summary=summary,
            overall_risk=overall_risk,
            scanned_at=datetime.now(timezone.utc),
            inspector_version=cls.INSPECTOR_VERSION,
            llm_augmented=llm_augmented,
            notes=notes or [],
        )

    @staticmethod
    def _compute_overall_risk(summary: dict[str, int]) -> str:
        if summary.get("critical", 0) > 0:
            return "critical"
        if summary.get("high", 0) > 0:
            return "high"
        if summary.get("medium", 0) > 0:
            return "medium"
        if summary.get("low", 0) > 0:
            return "low"
        return "minimal"
