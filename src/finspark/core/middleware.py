"""Middleware for tenant isolation, logging, and request processing."""

from __future__ import annotations

import logging
import re
import time

from fastapi import Request
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"
DEFAULT_TENANT_NAME = "Default Tenant"


class TenantMiddleware(BaseHTTPMiddleware):
    """Extracts tenant context from request headers and injects into request state."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        tenant_id = request.headers.get("X-Tenant-ID", DEFAULT_TENANT_ID)
        tenant_name = request.headers.get("X-Tenant-Name", DEFAULT_TENANT_NAME)
        role = request.headers.get("X-Tenant-Role", "admin")

        request.state.tenant_id = tenant_id
        request.state.tenant_name = tenant_name
        request.state.role = role

        response = await call_next(request)
        response.headers["X-Tenant-ID"] = tenant_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs request details and timing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.monotonic()
        response = await call_next(request)
        duration = round((time.monotonic() - start_time) * 1000, 2)

        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration,
                "tenant_id": getattr(request.state, "tenant_id", "unknown"),
            },
        )

        response.headers["X-Response-Time"] = f"{duration}ms"
        return response


# Pattern: /api/v1/adapters/{adapter_id}/versions/{version}/...
_ADAPTER_VERSION_RE = re.compile(r"^/api/v1/adapters/([^/]+)/versions/([^/]+)")


class DeprecationHeaderMiddleware(BaseHTTPMiddleware):
    """Adds Sunset and Deprecation headers when a deprecated adapter version is referenced."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        match = _ADAPTER_VERSION_RE.match(request.url.path)
        if not match:
            return response

        adapter_id = match.group(1)
        version_str = match.group(2)

        try:
            from finspark.core.database import async_session_factory
            from finspark.models.adapter import AdapterVersion
            from finspark.services.registry.deprecation import DeprecationTracker

            async with async_session_factory() as db:
                stmt = select(AdapterVersion).where(
                    AdapterVersion.adapter_id == adapter_id,
                    AdapterVersion.version == version_str,
                )
                result = await db.execute(stmt)
                version = result.scalar_one_or_none()

                if version and version.status == "deprecated":
                    tracker = DeprecationTracker(db)
                    sunset_date = tracker._compute_sunset_date(version)
                    if sunset_date:
                        response.headers["Sunset"] = sunset_date.strftime(
                            "%a, %d %b %Y %H:%M:%S GMT"
                        )
                    response.headers["Deprecation"] = "true"
                    replacement = await tracker._find_replacement(adapter_id, version)
                    if replacement:
                        response.headers["Link"] = (
                            f'</api/v1/adapters/{adapter_id}/versions/{replacement}>; rel="successor-version"'
                        )
        except Exception:
            logger.warning("Failed to check deprecation headers", exc_info=True)

        return response
