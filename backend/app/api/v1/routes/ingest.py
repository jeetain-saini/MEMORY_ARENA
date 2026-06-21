"""Ingestion API endpoint (API v1).

``POST /ingest`` accepts raw conversation/document text and enqueues an async
extraction job (LangGraph/sequential workflow -> CreateMemoryUseCase). It returns
**202 Accepted** with a job id immediately; extraction and persistence happen off
the request path on the workflow job processor.

No LLM call happens inside the request; this is extraction ingestion only —
not a chat agent, RAG, or query-time workflow.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, status

from app.api.v1.dependencies.providers import CurrentPrincipalDep, WorkflowProcessorDep
from app.application.dto.auth_dto import AuthPrincipal
from app.application.interfaces.workflow_job_processor import WorkflowJob, WorkflowJobProcessor
from app.application.services.authorization import resolve_scope
from app.core.logging import get_request_id
from app.schemas.ingest import IngestAcceptedSchema, IngestRequestSchema
from app.schemas.responses import APIResponse

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=APIResponse[IngestAcceptedSchema],
    summary="Ingest raw text: extract memories asynchronously",
)
async def ingest(
    payload: IngestRequestSchema,
    processor: WorkflowJobProcessor = WorkflowProcessorDep,
    principal: AuthPrincipal | None = CurrentPrincipalDep,
) -> APIResponse[IngestAcceptedSchema]:
    # No authenticated user may create memories for another user. Enforced
    # synchronously here because ingestion is processed off the request path.
    resolve_scope(principal, payload.user_id)
    job_id = uuid4()
    await processor.submit(
        WorkflowJob(job_id=job_id, user_id=payload.user_id, raw_text=payload.text)
    )
    return APIResponse(
        data=IngestAcceptedSchema(job_id=job_id, status="queued"),
        request_id=get_request_id(),
    )
