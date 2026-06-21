"""Query-Time Agent API endpoints (API v1).

``POST /query`` runs the agent to completion and returns ``{answer, citations}``
in the standard envelope. ``POST /query/stream`` runs the same agent but streams
progress as Server-Sent Events: a ``step`` per stage, then ``answer``,
``citations``, and a terminal ``done`` (with ``error`` before it on failure).

The agent orchestrates the existing MemoryArena pipeline (retrieval → graph
expansion → context assembly → LLM compression → generation); it adds no new
capability and never bypasses those subsystems.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.v1.dependencies.providers import AgentConfigDep, QueryUseCaseDep
from app.application.dto.agent_dto import AgentConfig, AgentStreamEvent
from app.application.use_cases.query_memory_use_cases import QueryMemoryUseCase
from app.core.logging import get_request_id
from app.schemas.query import QueryRequestSchema, QueryResponseSchema
from app.schemas.responses import APIResponse

router = APIRouter(prefix="/query", tags=["query"])


@router.post(
    "",
    response_model=APIResponse[QueryResponseSchema],
    summary="Answer a query using the memory agent",
)
async def query(
    payload: QueryRequestSchema,
    use_case: QueryMemoryUseCase = QueryUseCaseDep,
    config: AgentConfig = AgentConfigDep,
) -> APIResponse[QueryResponseSchema]:
    response = await use_case.execute(payload.to_request(config))
    return APIResponse(
        data=QueryResponseSchema.from_dto(response),
        request_id=get_request_id(),
    )


def _sse_frame(event: AgentStreamEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"


@router.post(
    "/stream",
    summary="Answer a query, streaming progress as Server-Sent Events",
)
async def query_stream(
    payload: QueryRequestSchema,
    use_case: QueryMemoryUseCase = QueryUseCaseDep,
    config: AgentConfig = AgentConfigDep,
) -> StreamingResponse:
    request = payload.to_request(config)
    # Resolve the stream (and its synchronous authorization scope check) before
    # returning the streaming response, so an unauthorized request yields a clean
    # 403 status rather than an in-band SSE error frame.
    events = use_case.stream(request)

    async def event_source() -> AsyncIterator[str]:
        try:
            async for event in events:
                yield _sse_frame(event)
        except Exception as exc:  # noqa: BLE001 — propagate as a final error frame
            yield _sse_frame(AgentStreamEvent(event="error", data={"message": str(exc)}))
            yield _sse_frame(AgentStreamEvent(event="done", data={"finish_reason": "error"}))

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
