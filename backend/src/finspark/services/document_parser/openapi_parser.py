"""
OpenAPI / Swagger YAML + JSON parser.

Supports:
- OpenAPI 3.x (application/json, application/yaml)
- Swagger 2.0

Extracts:
- All path + method combinations → ApiEndpoint
- Security schemes → AuthRequirement
- Schema properties → FieldDefinition
- Server URLs, external docs, tags
- Flat section list for unified model compatibility
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any, Union

import yaml  # PyYAML is a transitive dep of many packages; add if needed

from finspark.models.parsed_document import (
    ApiEndpoint,
    AuthRequirement,
    AuthScheme,
    DocumentSection,
    DocumentType,
    FieldDefinition,
    HttpMethod,
    ParsedDocument,
    SectionCategory,
    TableData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_METHODS = {m.value for m in HttpMethod}

_SECURITY_SCHEME_MAP: dict[str, AuthScheme] = {
    "apikey": AuthScheme.API_KEY,
    "api_key": AuthScheme.API_KEY,
    "http": AuthScheme.BEARER,
    "bearer": AuthScheme.BEARER,
    "basic": AuthScheme.BASIC,
    "oauth2": AuthScheme.OAUTH2,
    "openidconnect": AuthScheme.OAUTH2,
}


def _load_spec(raw: str | bytes) -> dict[str, Any]:
    """Try JSON first, then YAML."""
    text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)  # type: ignore[return-value]
    return yaml.safe_load(text)  # type: ignore[return-value]


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a simple $ref like '#/components/schemas/Foo'."""
    if not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for part in parts:
        if not isinstance(node, dict):
            return {}
        node = node.get(part.replace("~1", "/").replace("~0", "~"), {})
    return node if isinstance(node, dict) else {}


def _extract_fields_from_schema(
    schema: dict[str, Any],
    spec: dict[str, Any],
    prefix: str = "",
    depth: int = 0,
) -> list[FieldDefinition]:
    if depth > 4:
        return []
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])

    fields: list[FieldDefinition] = []
    props = schema.get("properties", {})
    required_set = set(schema.get("required", []))

    for name, prop in props.items():
        if "$ref" in prop:
            prop = _resolve_ref(spec, prop["$ref"])
        full_name = f"{prefix}.{name}" if prefix else name
        fields.append(
            FieldDefinition(
                name=full_name,
                field_type=prop.get("type", prop.get("$ref", "object").split("/")[-1]),
                required=name in required_set,
                description=prop.get("description", ""),
                example=str(prop.get("example", "")),
                constraints={
                    k: v
                    for k, v in prop.items()
                    if k in ("minLength", "maxLength", "minimum", "maximum", "pattern", "enum", "format")
                },
            )
        )
        # Recurse into nested objects
        if prop.get("type") == "object" or "properties" in prop:
            fields.extend(
                _extract_fields_from_schema(prop, spec, prefix=full_name, depth=depth + 1)
            )
    return fields


def _parse_security_schemes(
    spec: dict[str, Any],
) -> list[AuthRequirement]:
    """Works for both OpenAPI 3 (components.securitySchemes) and Swagger 2 (securityDefinitions)."""
    schemes_raw: dict[str, Any] = {}

    # OpenAPI 3
    components = spec.get("components", {})
    schemes_raw.update(components.get("securitySchemes", {}))
    # Swagger 2
    schemes_raw.update(spec.get("securityDefinitions", {}))

    reqs: list[AuthRequirement] = []
    for _name, defn in schemes_raw.items():
        if not isinstance(defn, dict):
            continue
        scheme_type = defn.get("type", "").lower()
        scheme_sub = defn.get("scheme", "").lower()
        # Combine type + scheme for http bearer vs http basic
        mapped = _SECURITY_SCHEME_MAP.get(scheme_sub) or _SECURITY_SCHEME_MAP.get(scheme_type, AuthScheme.NONE)

        # Extract OAuth2 token URLs
        token_url = ""
        flows = defn.get("flows", {})
        for flow in flows.values():
            if isinstance(flow, dict) and "tokenUrl" in flow:
                token_url = flow["tokenUrl"]
                break

        scopes: list[str] = []
        for flow in flows.values():
            if isinstance(flow, dict):
                scopes.extend(flow.get("scopes", {}).keys())

        reqs.append(
            AuthRequirement(
                scheme=mapped,
                description=defn.get("description", ""),
                header_name=defn.get("name", ""),
                scopes=scopes,
                token_url=token_url,
            )
        )

    return reqs or [AuthRequirement(scheme=AuthScheme.NONE)]


def _is_auth_required(operation: dict[str, Any], global_security: list[Any]) -> bool:
    op_security = operation.get("security")
    if op_security is not None:
        return bool(op_security)
    return bool(global_security)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_openapi(source: Union[str, Path, bytes, io.BytesIO], filename: str = "") -> ParsedDocument:
    if isinstance(source, io.BytesIO):
        raw = source.read()
    elif isinstance(source, bytes):
        raw = source
    elif isinstance(source, Path):
        raw = source.read_bytes()
        filename = filename or source.name
    else:
        raw = Path(source).read_bytes()
        filename = filename or str(source)

    doc_type = DocumentType.OPENAPI_YAML
    if filename.endswith(".json") or (isinstance(raw, bytes) and raw.lstrip()[:1] == b"{"):
        doc_type = DocumentType.OPENAPI_JSON

    try:
        spec: dict[str, Any] = _load_spec(raw)
    except Exception as exc:
        return ParsedDocument(
            source_filename=filename,
            doc_type=doc_type,
            parse_errors=[f"Failed to parse spec: {exc}"],
        )

    if not isinstance(spec, dict):
        return ParsedDocument(
            source_filename=filename,
            doc_type=doc_type,
            parse_errors=["Spec root is not an object/dict"],
        )

    # -----------------------------------------------------------------------
    # Top-level metadata
    # -----------------------------------------------------------------------
    info: dict[str, Any] = spec.get("info", {})
    title = info.get("title", "")
    version = info.get("version", "")
    description = info.get("description", "")
    openapi_version = spec.get("openapi", spec.get("swagger", ""))

    # Server / base URLs
    base_urls: list[str] = []
    if "servers" in spec:
        base_urls = [s.get("url", "") for s in spec["servers"] if isinstance(s, dict)]
    elif "host" in spec:
        scheme = spec.get("schemes", ["https"])[0]
        base_path = spec.get("basePath", "")
        base_urls = [f"{scheme}://{spec['host']}{base_path}"]

    external_docs: list[str] = []
    ext = spec.get("externalDocs")
    if isinstance(ext, dict) and ext.get("url"):
        external_docs.append(ext["url"])

    global_security = spec.get("security", [])

    # -----------------------------------------------------------------------
    # Paths → endpoints
    # -----------------------------------------------------------------------
    endpoints: list[ApiEndpoint] = []
    paths: dict[str, Any] = spec.get("paths", {})

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        # Shared parameters at path level
        path_params: list[dict[str, Any]] = path_item.get("parameters", [])

        for method_raw, operation in path_item.items():
            if method_raw.upper() not in _VALID_METHODS:
                continue
            if not isinstance(operation, dict):
                continue

            op_params: list[dict[str, Any]] = operation.get("parameters", [])
            all_params = path_params + op_params

            # Request body
            req_body: dict[str, Any] | None = None
            rb = operation.get("requestBody", {})
            if rb:
                content = rb.get("content", {})
                for media_type, media_obj in content.items():
                    if isinstance(media_obj, dict) and "schema" in media_obj:
                        req_body = media_obj["schema"]
                        break

            # Responses
            response_schemas: dict[str, dict[str, Any]] = {}
            for status, resp in operation.get("responses", {}).items():
                if isinstance(resp, dict):
                    resp_content = resp.get("content", {})
                    for media_type, media_obj in resp_content.items():
                        if isinstance(media_obj, dict) and "schema" in media_obj:
                            response_schemas[str(status)] = media_obj["schema"]
                            break

            endpoints.append(
                ApiEndpoint(
                    path=path,
                    method=HttpMethod(method_raw.upper()),
                    summary=operation.get("summary", ""),
                    description=operation.get("description", ""),
                    tags=operation.get("tags", []),
                    parameters=all_params,
                    request_body_schema=req_body,
                    response_schemas=response_schemas,
                    auth_required=_is_auth_required(operation, global_security),
                    source_section="paths",
                )
            )

    # -----------------------------------------------------------------------
    # Field definitions from all schemas
    # -----------------------------------------------------------------------
    field_definitions: list[FieldDefinition] = []
    schemas: dict[str, Any] = spec.get("components", {}).get("schemas", {})
    # Swagger 2
    schemas.update(spec.get("definitions", {}))

    for schema_name, schema_def in schemas.items():
        if not isinstance(schema_def, dict):
            continue
        field_definitions.extend(
            _extract_fields_from_schema(schema_def, spec, prefix=schema_name)
        )

    # -----------------------------------------------------------------------
    # Auth
    # -----------------------------------------------------------------------
    auth_requirements = _parse_security_schemes(spec)

    # -----------------------------------------------------------------------
    # Sections (one per tag, plus a generic one for paths without tags)
    # -----------------------------------------------------------------------
    tag_groups: dict[str, list[ApiEndpoint]] = {}
    for ep in endpoints:
        for tag in (ep.tags or ["untagged"]):
            tag_groups.setdefault(tag, []).append(ep)

    sections: list[DocumentSection] = []
    for tag, tag_endpoints in tag_groups.items():
        content_lines = [f"{ep.method.value} {ep.path}  — {ep.summary}" for ep in tag_endpoints]
        content = "\n".join(content_lines)
        sections.append(
            DocumentSection(
                heading=tag,
                level=1,
                category=SectionCategory.ENDPOINTS,
                content=content,
                api_paths=[ep.path for ep in tag_endpoints],
            )
        )

    # Schema section
    if schemas:
        schema_content = "\n".join(schemas.keys())
        sections.append(
            DocumentSection(
                heading="Schemas / Definitions",
                level=1,
                category=SectionCategory.DATA_FORMAT,
                content=schema_content,
                field_names=[fd.name for fd in field_definitions],
            )
        )

    # Auth section
    if auth_requirements:
        sections.append(
            DocumentSection(
                heading="Security",
                level=1,
                category=SectionCategory.AUTHENTICATION,
                content="\n".join(str(ar) for ar in auth_requirements),
            )
        )

    raw_text = f"Title: {title}\nVersion: {version}\n{description}"

    return ParsedDocument(
        source_filename=filename,
        doc_type=doc_type,
        title=title,
        version=version,
        description=description,
        openapi_version=openapi_version,
        base_urls=base_urls,
        external_docs=external_docs,
        sections=sections,
        endpoints=endpoints,
        auth_requirements=auth_requirements,
        field_definitions=field_definitions,
        all_api_paths=[ep.path for ep in endpoints],
        all_urls=base_urls + external_docs,
        all_field_names=list({fd.name for fd in field_definitions}),
        raw_text=raw_text,
    )
