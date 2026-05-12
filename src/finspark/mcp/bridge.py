"""In-process bridge between MCP tools and AdaptConfig service classes.

The three persona-spec'd tools (``list_adapters``, ``generate_config``,
``invoke``) reuse :class:`DocumentParser`, :class:`ConfigGenerator`, and
:class:`IntegrationSimulator` directly — they do **not** call back into the
FastAPI app over HTTP.

A dedicated stdio process has no FastAPI tenant context, so a synthetic
``MCP_TENANT_ID`` (``"mcp"``) namespace is used for all persisted rows.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from finspark.core.database import async_session_factory, init_db
from finspark.models.adapter import Adapter, AdapterVersion
from finspark.models.configuration import Configuration, ConfigurationHistory
from finspark.seeds import seed_adapters as _seed_adapters

logger = logging.getLogger(__name__)

MCP_TENANT_ID = "mcp"
_SEED_FILE = Path(__file__).resolve().parent.parent / "seeds" / "adapters.json"

_init_lock = asyncio.Lock()
_initialized = False


# ---------------------------------------------------------------------------
# Lazy DB bootstrap
# ---------------------------------------------------------------------------


async def _ensure_initialized() -> None:
    """Initialize schema and seed adapters on first use of the MCP bridge.

    Idempotent: ``init_db`` uses ``create_all`` (no-op when tables exist) and
    ``seed_adapters`` skips when any adapter row is already present.
    """
    global _initialized  # noqa: PLW0603
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return
        await init_db()
        await _seed_adapters()
        _initialized = True


def _load_seed_adapters() -> list[dict[str, Any]]:
    """Load the adapter catalog from the bundled JSON seed file."""
    with open(_SEED_FILE) as f:
        return list(json.load(f))


# ---------------------------------------------------------------------------
# Adapter selection
# ---------------------------------------------------------------------------


def _score_adapter(adapter: Adapter, hint: str) -> float:
    """Score an adapter against a free-form hint (case-insensitive token match)."""
    hint_lower = hint.lower()
    if not hint_lower:
        return 0.0
    tokens = [t for t in hint_lower.replace("-", " ").replace("_", " ").split() if t]
    score = 0.0
    name_lower = (adapter.name or "").lower()
    desc_lower = (adapter.description or "").lower()
    cat_lower = (adapter.category or "").lower()
    for token in tokens:
        if token in name_lower:
            score += 3.0
        if token in cat_lower:
            score += 2.0
        if token in desc_lower:
            score += 1.0
    return score


def _latest_version(adapter: Adapter) -> AdapterVersion | None:
    """Return the newest active version of an adapter, or None."""
    versions = sorted(
        [v for v in adapter.versions if v.status == "active"],
        key=lambda v: (v.version_order or 0, v.version),
        reverse=True,
    )
    return versions[0] if versions else (
        sorted(adapter.versions, key=lambda v: v.version, reverse=True)[0]
        if adapter.versions
        else None
    )


# ---------------------------------------------------------------------------
# Tool 1: list_adapters
# ---------------------------------------------------------------------------


async def list_adapters_tool() -> list[dict[str, Any]]:
    """Return the adapter catalogue with one row per adapter.

    Each row contains: ``id``, ``name``, ``category``, ``description``,
    ``latest_version_id`` and ``latest_version``. Reads from the DB so MCP
    callers see the same ids the FastAPI app sees.
    """
    await _ensure_initialized()
    async with async_session_factory() as session:
        stmt = select(Adapter).options(selectinload(Adapter.versions)).order_by(Adapter.name)
        result = await session.execute(stmt)
        adapters = list(result.scalars().all())

        rows: list[dict[str, Any]] = []
        for adapter in adapters:
            latest = _latest_version(adapter)
            rows.append(
                {
                    "id": adapter.id,
                    "name": adapter.name,
                    "category": adapter.category,
                    "description": adapter.description or "",
                    "latest_version_id": latest.id if latest else None,
                    "latest_version": latest.version if latest else None,
                }
            )
        return rows


# ---------------------------------------------------------------------------
# Tool 2: generate_config
# ---------------------------------------------------------------------------


async def _pick_adapter(
    session: Any, adapter_hint: str | None
) -> Adapter | None:
    """Resolve an adapter from a hint by id, exact name, or fuzzy match."""
    if adapter_hint:
        # Try direct id
        by_id = await session.execute(
            select(Adapter)
            .options(selectinload(Adapter.versions))
            .where(Adapter.id == adapter_hint)
        )
        adapter = by_id.scalar_one_or_none()
        if adapter is not None:
            return adapter

    # Load all and pick by score (or first when no hint)
    stmt = select(Adapter).options(selectinload(Adapter.versions))
    result = await session.execute(stmt)
    adapters = list(result.scalars().all())
    if not adapters:
        return None
    if not adapter_hint:
        return adapters[0]

    scored = [(a, _score_adapter(a, adapter_hint)) for a in adapters]
    scored.sort(key=lambda t: t[1], reverse=True)
    top, top_score = scored[0]
    if top_score <= 0:
        return None
    return top


def _adapter_version_payload(version: AdapterVersion) -> dict[str, Any]:
    """Convert an AdapterVersion row into the dict ConfigGenerator expects."""
    return {
        "adapter_name": version.adapter_id,
        "version": version.version,
        "base_url": version.base_url or "",
        "auth_type": version.auth_type,
        "endpoints": json.loads(version.endpoints) if version.endpoints else [],
        "request_schema": json.loads(version.request_schema)
        if version.request_schema
        else {},
        "response_schema": json.loads(version.response_schema)
        if version.response_schema
        else {},
    }


async def generate_config_tool(
    document_text: str,
    adapter_hint: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Parse a document, pick an adapter, generate a config, persist it.

    Returns ``{config_id, adapter_id, adapter_name, adapter_version,
    name, config}``. The config is the same payload that FastAPI's
    ``/configurations/generate`` returns under ``data``.

    Falls back to the rule-based ``ConfigGenerator`` whenever the LLM path is
    unavailable, so the tool stays usable without an API key.
    """
    from finspark.services.config_engine.field_mapper import ConfigGenerator
    from finspark.services.parsing.document_parser import DocumentParser

    if not isinstance(document_text, str) or not document_text.strip():
        return {"error": "document_text must be a non-empty string"}

    await _ensure_initialized()

    async with async_session_factory() as session:
        adapter = await _pick_adapter(session, adapter_hint)
        if adapter is None:
            return {
                "error": (
                    f"No adapter matched hint {adapter_hint!r}"
                    if adapter_hint
                    else "Adapter catalogue is empty"
                )
            }
        version = _latest_version(adapter)
        if version is None:
            return {"error": f"Adapter {adapter.name!r} has no versions"}

        # Parse document (LLM with regex fallback)
        parser = DocumentParser()
        parsed_dict: dict[str, Any]
        try:
            from finspark.services.llm.client import get_llm_client

            client = get_llm_client()
            parsed = await parser.parse_with_llm(document_text, "document.txt", client)
            parsed_dict = parsed.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.info("LLM parsing unavailable (%s); using regex fallback", exc)
            parsed = parser.parse_text(document_text)
            parsed_dict = parsed.model_dump(mode="json")

        # Generate config via the rule-based engine (deterministic, no network)
        av_payload = _adapter_version_payload(version)
        generator = ConfigGenerator()
        config = await asyncio.to_thread(generator.generate, parsed_dict, av_payload)

        # Ensure simulator-required keys exist (matches FastAPI route behaviour)
        config.setdefault("adapter_name", adapter.name)
        config.setdefault("version", version.version)
        config.setdefault("base_url", version.base_url or "")
        config.setdefault(
            "auth",
            {"type": version.auth_type, "credentials": {}},
        )

        config_name = name or (
            f"MCP {adapter.name} {datetime.now(UTC).isoformat(timespec='seconds')}"
        )

        configuration = Configuration(
            tenant_id=MCP_TENANT_ID,
            name=config_name,
            adapter_version_id=version.id,
            document_id=None,
            status="configured",
            version=1,
            field_mappings=json.dumps(config.get("field_mappings", [])),
            transformation_rules=json.dumps(config.get("transformation_rules", [])),
            hooks=json.dumps(config.get("hooks", [])),
            full_config=json.dumps(config),
        )
        session.add(configuration)
        await session.flush()

        history = ConfigurationHistory(
            tenant_id=MCP_TENANT_ID,
            configuration_id=configuration.id,
            version=1,
            change_type="created",
            new_value=json.dumps(config),
            changed_by="mcp",
        )
        session.add(history)
        await session.commit()

        return {
            "config_id": configuration.id,
            "adapter_id": adapter.id,
            "adapter_name": adapter.name,
            "adapter_version": version.version,
            "adapter_version_id": version.id,
            "name": configuration.name,
            "config": config,
        }


# ---------------------------------------------------------------------------
# Tool 3: invoke
# ---------------------------------------------------------------------------


async def invoke_tool(
    config_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the persisted config against deterministic mock responses.

    The persona spec calls for "the chain executor / mock responses against
    the persisted config." We load the config row, build the endpoint list
    from ``full_config``, and run :func:`execute_chain` with a call_fn that
    proxies to :class:`MockAPIServer`. Inputs in ``payload`` are merged into
    each endpoint's request body so chain templates can reference them.

    Returns ``{config_id, adapter_name, adapter_version, endpoint_count,
    steps, final, status}`` where ``status`` is ``"ok"`` on full success and
    ``"error"`` on any chain failure.
    """
    if not isinstance(config_id, str) or not config_id:
        return {"error": "config_id must be a non-empty string"}

    payload = payload or {}
    if not isinstance(payload, dict):
        return {"error": "payload must be a JSON object"}

    await _ensure_initialized()

    async with async_session_factory() as session:
        stmt = select(Configuration).where(Configuration.id == config_id)
        result = await session.execute(stmt)
        configuration = result.scalar_one_or_none()
        if configuration is None:
            return {"error": f"Configuration {config_id!r} not found"}

        try:
            full_config: dict[str, Any] = (
                json.loads(configuration.full_config) if configuration.full_config else {}
            )
        except json.JSONDecodeError as exc:
            return {"error": f"Configuration payload is not valid JSON: {exc}"}

        endpoints: list[dict[str, Any]] = list(full_config.get("endpoints", []) or [])
        adapter_name = full_config.get("adapter_name") or ""
        adapter_version = full_config.get("version") or ""

        if not endpoints:
            return {
                "config_id": config_id,
                "adapter_name": adapter_name,
                "adapter_version": adapter_version,
                "endpoint_count": 0,
                "steps": [],
                "final": None,
                "status": "ok",
            }

        # Lazy imports — keep server start-up cheap.
        from finspark.services.chain_executor import (
            ChainExecutionError,
            execute_chain,
        )
        from finspark.services.simulation.simulator import MockAPIServer

        mock = MockAPIServer()

        # Merge MCP-supplied payload into each endpoint's request body so the
        # chain executor passes it through as the request template.
        prepared_endpoints: list[dict[str, Any]] = []
        for ep in endpoints:
            ep_copy = dict(ep)
            ep_copy.setdefault("id", ep.get("path", "step").lstrip("/").replace("/", "_"))
            existing_body = ep_copy.get("body") or {}
            merged_body = {**existing_body, **payload}
            ep_copy["body"] = merged_body
            prepared_endpoints.append(ep_copy)

        async def _call_fn(
            endpoint: dict[str, Any], prepared_request: dict[str, Any]
        ) -> dict[str, Any]:
            return await asyncio.to_thread(
                mock.generate_response, endpoint, prepared_request, None, full_config
            )

        try:
            chain_results = await execute_chain(prepared_endpoints, _call_fn)
        except ChainExecutionError as exc:
            return {
                "config_id": config_id,
                "adapter_name": adapter_name,
                "adapter_version": adapter_version,
                "endpoint_count": len(prepared_endpoints),
                "steps": [],
                "final": None,
                "status": "error",
                "error": str(exc),
            }

        final_response = chain_results[-1]["response"] if chain_results else None
        return {
            "config_id": config_id,
            "adapter_name": adapter_name,
            "adapter_version": adapter_version,
            "endpoint_count": len(prepared_endpoints),
            "steps": chain_results,
            "final": final_response,
            "status": "ok",
        }
