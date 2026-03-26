"""
Shared regex patterns and heuristic helpers used by all parsers.
"""
from __future__ import annotations

import re
from typing import Final

from finspark.models.parsed_document import AuthScheme, SectionCategory


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_URL_RE: Final = re.compile(
    r"https?://[^\s\"'<>\])\}]+"
)

_API_PATH_RE: Final = re.compile(
    r"(?<![a-zA-Z0-9])(/(?:api|v\d+|rest|graphql|ws)[/\w\-\{\}:@!$&'()*+,;=%.~]*)"
    r"|(?<![a-zA-Z0-9])(/\{[a-zA-Z_][a-zA-Z0-9_]*\}[/\w\-\{\}]*)"
)

_FIELD_NAME_RE: Final = re.compile(
    r"\b([a-z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+)\b"  # snake_case
    r"|\b([a-z][a-z0-9]*(?:[A-Z][a-z0-9]+)+)\b"    # camelCase
)

_VERSION_RE: Final = re.compile(
    r"(?:version|v)\s*[:\-]?\s*(\d+\.\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_HTTP_METHOD_RE: Final = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b"
    r"\s+([/\w\-\{\}:.%@?=&]+)",
    re.IGNORECASE,
)

_BEARER_RE: Final = re.compile(
    r"\bbearer\b|\bJWT\b|\bauthorization\s+header\b",
    re.IGNORECASE,
)
_API_KEY_RE: Final = re.compile(
    r"\bapi[\s_-]?key\b|\bx-api-key\b|\bapi_key\b",
    re.IGNORECASE,
)
_BASIC_RE: Final = re.compile(r"\bbasic\s+auth(?:entication)?\b", re.IGNORECASE)
_OAUTH_RE: Final = re.compile(r"\boauth\s*2?\.?\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Section classification keyword maps
# ---------------------------------------------------------------------------

_SECTION_KEYWORDS: Final[dict[SectionCategory, list[str]]] = {
    SectionCategory.REQUIREMENTS: [
        "requirement", "must", "shall", "should", "functional", "non-functional",
        "acceptance criteria", "user story", "use case",
    ],
    SectionCategory.TECHNICAL_SPEC: [
        "architecture", "design", "technical", "implementation", "component",
        "database", "schema", "data model", "infrastructure", "stack",
    ],
    SectionCategory.SECURITY: [
        "security", "encryption", "tls", "ssl", "certificate", "firewall",
        "vulnerability", "threat", "compliance", "pci", "gdpr", "hipaa",
        "audit", "intrusion", "penetration",
    ],
    SectionCategory.AUTHENTICATION: [
        "authentication", "authorization", "auth", "login", "token",
        "oauth", "jwt", "api key", "credential", "sso", "saml", "ldap",
        "mfa", "2fa", "session",
    ],
    SectionCategory.ENDPOINTS: [
        "endpoint", "api", "rest", "route", "path", "url", "webhook",
        "resource", "method", "http", "request", "response",
    ],
    SectionCategory.DATA_FORMAT: [
        "json", "xml", "csv", "yaml", "format", "field", "payload",
        "object", "array", "string", "integer", "boolean", "enum",
        "date", "timestamp", "uuid",
    ],
    SectionCategory.ERROR_HANDLING: [
        "error", "exception", "fault", "failure", "retry", "timeout",
        "status code", "4xx", "5xx", "fallback", "circuit breaker",
    ],
    SectionCategory.OVERVIEW: [
        "overview", "introduction", "summary", "background", "purpose",
        "scope", "objective", "goal", "executive",
    ],
    SectionCategory.GLOSSARY: [
        "glossary", "terminology", "definition", "abbreviation", "acronym",
    ],
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(_URL_RE.findall(text)))


def extract_api_paths(text: str) -> list[str]:
    paths: list[str] = []
    for m in _API_PATH_RE.finditer(text):
        path = m.group(1) or m.group(2)
        if path and len(path) > 1:
            paths.append(path)
    return list(dict.fromkeys(paths))


def extract_field_names(text: str) -> list[str]:
    names: list[str] = []
    for m in _FIELD_NAME_RE.finditer(text):
        name = m.group(1) or m.group(2)
        if name and len(name) > 3:
            names.append(name)
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def extract_version(text: str) -> str:
    m = _VERSION_RE.search(text)
    return m.group(1) if m else ""


def classify_section(heading: str, content: str) -> SectionCategory:
    combined = (heading + " " + content[:500]).lower()
    scores: dict[SectionCategory, int] = {}
    for category, keywords in _SECTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score:
            scores[category] = score
    if not scores:
        return SectionCategory.UNKNOWN
    return max(scores, key=lambda c: scores[c])


def detect_auth_schemes(text: str) -> list[AuthScheme]:
    found: list[AuthScheme] = []
    if _OAUTH_RE.search(text):
        found.append(AuthScheme.OAUTH2)
    if _BEARER_RE.search(text):
        found.append(AuthScheme.BEARER)
    if _API_KEY_RE.search(text):
        found.append(AuthScheme.API_KEY)
    if _BASIC_RE.search(text):
        found.append(AuthScheme.BASIC)
    return found


def detect_http_method_pairs(text: str) -> list[tuple[str, str]]:
    """Return (METHOD, path) pairs found in free text."""
    return [
        (m.group(1).upper(), m.group(2))
        for m in _HTTP_METHOD_RE.finditer(text)
    ]
