"""Analytics and metrics routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.api.dependencies import get_tenant_context
from finspark.core.database import get_db
from finspark.schemas.common import APIResponse, TenantContext
from finspark.services.analytics import AnalyticsService
from finspark.services.health_monitor import monitor

router = APIRouter(tags=["Analytics"])


@router.get("/api/v1/analytics/dashboard", response_model=APIResponse)
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
) -> APIResponse:
    """Get dashboard overview metrics for the current tenant."""
    service = AnalyticsService(db, tenant.tenant_id)
    metrics = await service.get_dashboard_metrics()
    return APIResponse(data=metrics)


@router.get("/api/v1/analytics/health")
async def get_platform_health() -> dict:
    """Get detailed platform health status."""
    return await monitor.run_all_checks()


@router.get("/metrics")
async def get_metrics() -> dict:
    """Prometheus-compatible metrics endpoint."""
    health = await monitor.run_all_checks()
    return {
        "uptime_seconds": health["uptime_seconds"],
        "healthy_checks": health["healthy"],
        "total_checks": health["total"],
    }
