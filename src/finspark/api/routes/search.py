"""Natural language search route for integrations."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from finspark.api.dependencies import get_tenant_context
from finspark.core.database import get_db
from finspark.schemas.common import APIResponse, TenantContext
from finspark.services.search import IntegrationSearch

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/", response_model=APIResponse[dict[str, Any]])
async def search_integrations(
    q: str = Query(..., min_length=1, description="Natural language search query"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Any = Depends(get_db),
) -> APIResponse[dict[str, Any]]:
    """Search adapters, configurations, and simulations using natural language."""
    search_service = IntegrationSearch(db)
    results = await search_service.search(query=q, tenant_id=tenant.tenant_id)

    def _result_to_dict(r: Any) -> dict[str, Any]:
        return {
            "type": r.type,
            "id": r.id,
            "name": r.name,
            "score": r.score,
            "details": r.details,
        }

    return APIResponse(
        data={
            "query": results.query,
            "total": results.total,
            "adapters": [_result_to_dict(r) for r in results.adapters],
            "configurations": [_result_to_dict(r) for r in results.configurations],
            "simulations": [_result_to_dict(r) for r in results.simulations],
        },
    )
