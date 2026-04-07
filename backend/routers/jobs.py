"""Document job status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.errors import api_error_response
from backend.models import JobResponse
from backend.routers.deps import RequestContext, get_request_context
from backend.services.jobs import get_job

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def job_status(
    job_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
):
    row = await get_job(context.owner_id, job_id)
    if not row:
        return api_error_response(
            request=request,
            status_code=404,
            error="Job not found.",
            code="JOB_NOT_FOUND",
            details={"job_id": job_id},
        )
    return JobResponse(**row)
