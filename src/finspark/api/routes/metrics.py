"""Authenticated metrics endpoint.

Replaces the unauthenticated ``/metrics`` route currently defined in main.py.
The integration agent should remove the ``@app.get("/metrics")`` handler from
main.py and include this router instead.
"""

from fastapi import APIRouter

from finspark.api.dependencies import require_role
from finspark.core.rate_limiter import metrics
from finspark.schemas.common import TenantContext

router = APIRouter(tags=["Metrics"])


@router.get("/metrics")
async def get_metrics(
    tenant: TenantContext = require_role("admin"),
) -> dict:
    """Return in-memory API metrics. Requires admin role."""
    return await metrics.snapshot()
