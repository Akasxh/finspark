"""
Top-level v1 API router.

All sub-routers are mounted here with their prefix and tags.
The health router is prefix-free because its paths already contain /health.
"""
from fastapi import APIRouter

from finspark.api.v1.endpoints import (
    adapters,
    audit,
    configurations,
    documents,
    health,
    hooks,
    simulations,
    tenants,
)

api_router = APIRouter(prefix="/v1")

# No extra prefix — health.router owns /health and /health/ready etc.
api_router.include_router(health.router)

api_router.include_router(documents.router)       # /v1/documents/...
api_router.include_router(adapters.router)        # /v1/adapters/...
api_router.include_router(configurations.router)  # /v1/configurations/...
api_router.include_router(simulations.router)     # /v1/simulations/...
api_router.include_router(tenants.router)         # /v1/tenants/...
api_router.include_router(audit.router)           # /v1/audit/...
api_router.include_router(hooks.router)           # /v1/hooks/...
