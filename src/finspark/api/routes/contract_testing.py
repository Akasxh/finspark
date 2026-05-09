"""Contract testing routes — run live API tests and view results."""

import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.api.dependencies import get_tenant_context, require_role
from finspark.core.database import get_db
from finspark.models.contract_test import ContractTestRun
from finspark.schemas.common import APIResponse
from finspark.schemas.testing import (
    ContractTestResultResponse,
    ContractTestRunResponse,
    DriftFieldResponse,
    RunContractTestRequest,
)
from finspark.services.testing.contract_tester import ContractTester

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contract-tests", tags=["contract-testing"])


@router.post("/{config_id}/run", response_model=APIResponse[ContractTestRunResponse])
async def run_contract_test(
    config_id: str,
    request: RunContractTestRequest | None = None,
    db: AsyncSession = Depends(get_db),
    tenant=require_role("admin", "editor"),
) -> APIResponse[ContractTestRunResponse]:
    """Run a live contract test against a configuration's endpoints."""
    body = request or RunContractTestRequest()
    tester = ContractTester(db)
    try:
        run_result = await tester.run_contract_test(
            config_id=config_id,
            tenant_id=tenant.tenant_id,
            sandbox_url=body.sandbox_url,
            sla_ms=body.sla_ms,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Persist to DB
    status = "passed" if run_result.failed == 0 else "failed"
    serialised_results = [asdict(r) for r in run_result.results]

    run_record = ContractTestRun(
        tenant_id=tenant.tenant_id,
        configuration_id=config_id,
        adapter_name=run_result.adapter_name,
        adapter_version=run_result.adapter_version,
        total_endpoints=run_result.total_endpoints,
        passed=run_result.passed,
        failed=run_result.failed,
        results=json.dumps(serialised_results),
        status=status,
    )
    db.add(run_record)
    await db.flush()

    # Build response
    result_responses = [
        ContractTestResultResponse(
            endpoint_path=r.endpoint_path,
            http_method=r.http_method,
            schema_valid=r.schema_valid,
            status_code=r.status_code,
            response_time_ms=r.response_time_ms,
            sla_ms=r.sla_ms,
            latency_ok=r.latency_ok,
            drift_report=[
                DriftFieldResponse(
                    field_path=d.field_path,
                    expected_type=d.expected_type,
                    actual_type=d.actual_type,
                    drift_type=d.drift_type,
                )
                for d in r.drift_report
            ],
            deprecation_warnings=r.deprecation_warnings,
            error=r.error,
        )
        for r in run_result.results
    ]

    return APIResponse(
        data=ContractTestRunResponse(
            id=run_record.id,
            configuration_id=config_id,
            adapter_name=run_result.adapter_name,
            adapter_version=run_result.adapter_version,
            total_endpoints=run_result.total_endpoints,
            passed=run_result.passed,
            failed=run_result.failed,
            status=status,
            results=result_responses,
            created_at=run_record.created_at,
        ),
        message=f"Contract test {status}: {run_result.passed}/{run_result.total_endpoints} endpoints passed",
    )


@router.get("/", response_model=APIResponse[list[ContractTestRunResponse]])
async def list_contract_test_runs(
    db: AsyncSession = Depends(get_db),
    tenant=Depends(get_tenant_context),
) -> APIResponse[list[ContractTestRunResponse]]:
    """List past contract test runs for the current tenant."""
    stmt = (
        select(ContractTestRun)
        .where(ContractTestRun.tenant_id == tenant.tenant_id)
        .order_by(ContractTestRun.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()

    data = []
    for run in runs:
        parsed_results: list[ContractTestResultResponse] = []
        if run.results:
            try:
                raw = json.loads(run.results)
                parsed_results = [
                    ContractTestResultResponse(
                        endpoint_path=r["endpoint_path"],
                        http_method=r["http_method"],
                        schema_valid=r["schema_valid"],
                        status_code=r["status_code"],
                        response_time_ms=r["response_time_ms"],
                        sla_ms=r.get("sla_ms"),
                        latency_ok=r["latency_ok"],
                        drift_report=[
                            DriftFieldResponse(**d) for d in r.get("drift_report", [])
                        ],
                        deprecation_warnings=r.get("deprecation_warnings", []),
                        error=r.get("error"),
                    )
                    for r in raw
                ]
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("Failed to parse results for run %s", run.id)

        data.append(
            ContractTestRunResponse(
                id=run.id,
                configuration_id=run.configuration_id,
                adapter_name=run.adapter_name,
                adapter_version=run.adapter_version,
                total_endpoints=run.total_endpoints,
                passed=run.passed,
                failed=run.failed,
                status=run.status,
                results=parsed_results,
                created_at=run.created_at,
            )
        )

    return APIResponse(success=True, data=data, message="")


@router.get("/{run_id}", response_model=APIResponse[ContractTestRunResponse])
async def get_contract_test_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    tenant=Depends(get_tenant_context),
) -> APIResponse[ContractTestRunResponse]:
    """Get details of a single contract test run."""
    stmt = select(ContractTestRun).where(
        ContractTestRun.id == run_id,
        ContractTestRun.tenant_id == tenant.tenant_id,
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Contract test run not found")

    parsed_results: list[ContractTestResultResponse] = []
    if run.results:
        try:
            raw = json.loads(run.results)
            parsed_results = [
                ContractTestResultResponse(
                    endpoint_path=r["endpoint_path"],
                    http_method=r["http_method"],
                    schema_valid=r["schema_valid"],
                    status_code=r["status_code"],
                    response_time_ms=r["response_time_ms"],
                    sla_ms=r.get("sla_ms"),
                    latency_ok=r["latency_ok"],
                    drift_report=[
                        DriftFieldResponse(**d) for d in r.get("drift_report", [])
                    ],
                    deprecation_warnings=r.get("deprecation_warnings", []),
                    error=r.get("error"),
                )
                for r in raw
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Failed to parse results for run %s", run.id)

    return APIResponse(
        data=ContractTestRunResponse(
            id=run.id,
            configuration_id=run.configuration_id,
            adapter_name=run.adapter_name,
            adapter_version=run.adapter_version,
            total_endpoints=run.total_endpoints,
            passed=run.passed,
            failed=run.failed,
            status=run.status,
            results=parsed_results,
            created_at=run.created_at,
        ),
    )
