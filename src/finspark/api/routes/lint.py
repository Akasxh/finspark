"""Ad-hoc API spec linting endpoint."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from finspark.schemas.common import APIResponse
from finspark.schemas.documents import LintReport
from finspark.services.lint.spectral_linter import lint_openapi_spec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lint", tags=["Lint"])


class LintRequest(BaseModel):
    """Request body for the ad-hoc lint endpoint."""

    spec_text: str
    format: str = "yaml"


@router.post("/", response_model=APIResponse[LintReport])
async def lint_spec(body: LintRequest) -> APIResponse[LintReport]:
    """Lint an OpenAPI/AsyncAPI spec and return findings."""
    report = await lint_openapi_spec(body.spec_text, format=body.format)
    return APIResponse(data=report)
