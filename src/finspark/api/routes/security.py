"""Security inspection endpoints for API specs and configs.

Design decision: security reports are NOT persisted to the config record.
They are computed on-demand and returned directly. This avoids schema
migrations and keeps the feature stateless. Clients can cache the report
if needed.
"""

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.api.dependencies import get_tenant_context
from finspark.core.config import settings
from finspark.core.database import get_db
from finspark.models.configuration import Configuration
from finspark.schemas.common import APIResponse, TenantContext
from finspark.schemas.security import SecurityReport
from finspark.services.security.inspector import SecurityInspector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["Security"])


class InspectSpecRequest(BaseModel):
    """Request body for spec inspection."""

    spec_text: str
    format: Literal["yaml", "json"] = "yaml"


def _get_llm_client_or_none():
    """Attempt to get the LLM client; return None if AI is disabled or unavailable."""
    if not settings.ai_enabled:
        return None
    try:
        from finspark.services.llm.client import get_llm_client
        return get_llm_client()
    except Exception:
        logger.warning("Could not initialize LLM client for security inspection", exc_info=True)
        return None


@router.post("/inspect-spec", response_model=APIResponse[SecurityReport])
async def inspect_spec(
    body: InspectSpecRequest,
    _tenant: TenantContext = Depends(get_tenant_context),
) -> APIResponse[SecurityReport]:
    """Inspect a raw API specification for security risks."""
    inspector = SecurityInspector()
    llm_client = _get_llm_client_or_none()
    report = await inspector.inspect_api_spec(body.spec_text, llm_client=llm_client)
    return APIResponse(
        success=True,
        data=report,
        message=f"Security inspection complete: {len(report.findings)} finding(s)",
    )


@router.post("/inspect-config/{config_id}", response_model=APIResponse[SecurityReport])
async def inspect_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> APIResponse[SecurityReport]:
    """Inspect an existing configuration for security risks."""
    result = await db.execute(
        select(Configuration).where(
            Configuration.id == config_id,
            Configuration.tenant_id == tenant.tenant_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuration not found")

    # Build a dict representation for the inspector.
    # DB stores JSON fields as text strings; parse them.
    def _parse_json_field(val: str | list | None) -> list:
        if val is None:
            return []
        if isinstance(val, list):
            return val
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    config_dict: dict = {
        "name": config.name,
        "status": config.status,
        "field_mappings": _parse_json_field(config.field_mappings),
        "transformation_rules": _parse_json_field(config.transformation_rules),
        "hooks": _parse_json_field(config.hooks),
    }
    # Pull adapter version info for richer inspection
    if hasattr(config, "adapter_version") and config.adapter_version:
        av = config.adapter_version
        config_dict["base_url"] = getattr(av, "base_url", "")
        config_dict["auth"] = {"type": getattr(av, "auth_type", "")}
        endpoints_raw = getattr(av, "endpoints", None)
        endpoints = _parse_json_field(endpoints_raw)
        config_dict["endpoints"] = [
            {"path": ep.get("path", ""), "method": ep.get("method", "GET")}
            for ep in endpoints
            if isinstance(ep, dict)
        ]

    inspector = SecurityInspector()
    llm_client = _get_llm_client_or_none()
    report = await inspector.inspect_config(config_dict, llm_client=llm_client)
    return APIResponse(
        success=True,
        data=report,
        message=f"Security inspection complete: {len(report.findings)} finding(s)",
    )
