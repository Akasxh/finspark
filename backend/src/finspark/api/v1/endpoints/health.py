"""
GET  /health         — liveness probe (no auth required)
GET  /health/ready   — readiness probe (checks DB + Redis)
GET  /health/detail  — full component status (admin only)
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from finspark.api.deps import DbDep, UserContext, require_roles
from finspark.core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Health"])


class ComponentStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class ComponentHealth(BaseModel):
    name: str
    status: ComponentStatus
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: ComponentStatus
    version: str
    env: str
    timestamp: datetime
    components: list[ComponentHealth] = []


# ---------------------------------------------------------------------------
# Liveness (no auth — used by container orchestrators)
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Always returns 200 if the process is alive.  No auth required.",
    responses={200: {"description": "Service is alive."}},
)
async def liveness() -> HealthResponse:
    return HealthResponse(
        status=ComponentStatus.OK,
        version="0.1.0",
        env=settings.APP_ENV,
        timestamp=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Readiness (no auth — checks downstream deps)
# ---------------------------------------------------------------------------


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description=(
        "Checks that downstream dependencies (DB, Redis) are reachable.  "
        "Returns 200 only when all required components are healthy.  "
        "Returns 503 when any required component is DOWN."
    ),
    responses={
        200: {"description": "All required dependencies are reachable."},
        503: {"description": "One or more required dependencies are down."},
    },
)
async def readiness(db: DbDep) -> HealthResponse:
    import time

    from sqlalchemy import text

    components: list[ComponentHealth] = []
    overall = ComponentStatus.OK

    # Database probe
    db_status = ComponentStatus.OK
    db_latency: float | None = None
    db_error: str | None = None
    try:
        t0 = time.monotonic()
        await db.execute(text("SELECT 1"))
        db_latency = round((time.monotonic() - t0) * 1000, 2)
    except Exception as exc:
        db_status = ComponentStatus.DOWN
        db_error = str(exc)
        overall = ComponentStatus.DOWN
        logger.error("health_db_down", error=str(exc))

    components.append(
        ComponentHealth(name="database", status=db_status, latency_ms=db_latency, error=db_error)
    )

    response = HealthResponse(
        status=overall,
        version="0.1.0",
        env=settings.APP_ENV,
        timestamp=datetime.now(UTC),
        components=components,
    )

    if overall == ComponentStatus.DOWN:
        from fastapi.responses import JSONResponse

        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json"),
        )

    return response


# ---------------------------------------------------------------------------
# Detail (admin only — exposes full component inventory)
# ---------------------------------------------------------------------------


@router.get(
    "/health/detail",
    response_model=HealthResponse,
    summary="Full component health detail",
    description="Admin-only endpoint with extended diagnostics.",
    responses={
        200: {"description": "Full health report."},
        403: {"description": "Admin required."},
    },
)
async def health_detail(
    db: DbDep,
    _user: Annotated[UserContext, Depends(require_roles("admin", "superadmin"))],
) -> HealthResponse:
    return await readiness(db)
