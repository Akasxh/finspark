"""
POST   /simulations/                         — start a simulation run
GET    /simulations/                         — list simulation runs (tenant-scoped)
GET    /simulations/{simulation_id}          — run status
GET    /simulations/{simulation_id}/results  — full results with per-step traces
POST   /simulations/{simulation_id}/cancel   — cancel a running simulation
"""
from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, status

from finspark.api.deps import CurrentUser, DbDep, PaginationDep, TenantCtx
from finspark.schemas.common import MessageResponse
from finspark.schemas.simulations import (
    SimulationDetail,
    SimulationListResponse,
    SimulationRecord,
    SimulationRunRequest,
    SimulationStatus,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/simulations", tags=["Simulations"])


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=SimulationRecord,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an integration simulation",
    description=(
        "Enqueues a simulation run for the given configuration.  "
        "The simulation executes in a sandboxed worker; external HTTP calls are "
        "intercepted by the mock layer unless `mock_external=false` (sandbox env only).  "
        "Poll GET /simulations/{id} or subscribe to `simulation.completed` hook."
    ),
    responses={
        202: {"description": "Simulation queued."},
        404: {"description": "Configuration not found."},
        403: {"description": "Tenant access denied."},
        409: {"description": "A simulation for this config is already running."},
    },
)
async def run_simulation(
    body: SimulationRunRequest,
    db: DbDep,
    _user: CurrentUser,
) -> SimulationRecord:
    # TODO: enqueue simulation task
    now = datetime.utcnow()
    return SimulationRecord(
        id=uuid.uuid4(),
        tenant_id=body.tenant_id,
        config_id=body.config_id,
        scenario=body.scenario,
        status=SimulationStatus.QUEUED,
        queued_at=now,
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=SimulationListResponse,
    summary="List simulation runs for a tenant",
    responses={200: {"description": "Paginated simulation records."}},
)
async def list_simulations(
    tenant_ctx: TenantCtx,
    db: DbDep,
    pagination: PaginationDep,
) -> SimulationListResponse:
    return SimulationListResponse(
        items=[],
        total=0,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=0,
    )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@router.get(
    "/{simulation_id}",
    response_model=SimulationRecord,
    summary="Get simulation run status",
    responses={
        200: {"description": "Simulation record with current status."},
        404: {"description": "Simulation not found."},
        403: {"description": "Tenant access denied."},
    },
)
async def get_simulation_status(
    simulation_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> SimulationRecord:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Simulation {simulation_id} not found.",
    )


# ---------------------------------------------------------------------------
# Full results
# ---------------------------------------------------------------------------


@router.get(
    "/{simulation_id}/results",
    response_model=SimulationDetail,
    summary="Get full simulation results with per-step traces",
    description=(
        "Only available once status is `passed` or `failed`.  "
        "Returns per-step request/response snapshots, assertion outcomes, "
        "and an optional coverage report URL."
    ),
    responses={
        200: {"description": "Full simulation detail."},
        404: {"description": "Simulation not found."},
        409: {"description": "Simulation not yet complete."},
        403: {"description": "Tenant access denied."},
    },
)
async def get_simulation_results(
    simulation_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> SimulationDetail:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Simulation {simulation_id} not found.",
    )


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@router.post(
    "/{simulation_id}/cancel",
    response_model=MessageResponse,
    summary="Cancel a running simulation",
    responses={
        200: {"description": "Cancellation requested."},
        404: {"description": "Simulation not found."},
        409: {"description": "Simulation is already complete."},
        403: {"description": "Tenant access denied."},
    },
)
async def cancel_simulation(
    simulation_id: UUID,
    tenant_ctx: TenantCtx,
    db: DbDep,
) -> MessageResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Simulation {simulation_id} not found.",
    )
