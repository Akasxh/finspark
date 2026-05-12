"""Health check route."""

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text
from starlette.responses import JSONResponse

from finspark.core.config import settings
from finspark.core.database import async_session_factory
from finspark.schemas.common import HealthCheck

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


async def _check_database() -> str:
    """Execute ``SELECT 1`` against the DB with a 2-second timeout.

    Returns ``"ok"`` on success or ``"error"`` on failure.
    """
    try:
        async with async_session_factory() as session:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")),
                timeout=2.0,
            )
        return "ok"
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        return "error"


@router.get("/health", response_model=HealthCheck)
async def health_check() -> HealthCheck | JSONResponse:
    db_status = await _check_database()

    status = "healthy" if db_status == "ok" else "degraded"
    health = HealthCheck(
        status=status,
        version=settings.app_version,
        timestamp=datetime.now(UTC),
        checks={"database": db_status, "ai_enabled": settings.ai_enabled},
    )

    if db_status != "ok":
        return JSONResponse(status_code=503, content=health.model_dump(mode="json"))

    return health
