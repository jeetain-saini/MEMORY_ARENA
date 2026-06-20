"""Observability API endpoints (API v1, Stage 13).

``GET /observability/traces`` lists the most recent request-scoped traces the
configured ``TraceRecorder`` is holding (newest first), optionally scoped to one
user. With the default in-memory recorder these are the recent ``/query`` runs;
with the no-op or LangSmith recorders the list is empty (traces are discarded or
shipped to LangSmith).

Thin presentation adapter: it reads from the recorder via its port and maps the
DTOs to schemas. No business logic.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.dependencies.providers import TraceRecorderDep
from app.application.interfaces.trace_recorder import TraceRecorder
from app.core.logging import get_request_id
from app.schemas.observability import RequestTraceSchema
from app.schemas.responses import APIResponse

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get(
    "/traces",
    response_model=APIResponse[list[RequestTraceSchema]],
    summary="List recent request-scoped observability traces (newest first)",
)
async def list_traces(
    recorder: TraceRecorder = TraceRecorderDep,
    limit: int = Query(default=50, ge=1, le=500),
    user_id: UUID | None = Query(default=None, description="Optional: scope to one user"),
) -> APIResponse[list[RequestTraceSchema]]:
    traces = await recorder.recent(limit=limit, user_id=user_id)
    return APIResponse(
        data=[RequestTraceSchema.from_dto(t) for t in traces],
        request_id=get_request_id(),
    )
