"""QueryMemoryUseCaseImpl — delegates to the AgentRuntime port.

Thin orchestration: it owns no retrieval/assembly/generation logic and no
infrastructure handles — it forwards to the injected ``AgentRuntime`` (selected
by configuration at the composition root) and returns plain DTOs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.application.dto.agent_dto import AgentRequest, AgentResponse, AgentStreamEvent
from app.application.interfaces.agent_runtime import AgentRuntime
from app.application.interfaces.trace_recorder import TraceRecorder
from app.application.use_cases.query_memory_use_cases import QueryMemoryUseCase


class QueryMemoryUseCaseImpl(QueryMemoryUseCase):
    def __init__(
        self, runtime: AgentRuntime, trace_recorder: TraceRecorder | None = None
    ) -> None:
        self._runtime = runtime
        self._recorder = trace_recorder

    async def execute(self, request: AgentRequest) -> AgentResponse:
        response = await self._runtime.respond(request)
        # Best-effort observability: record the request trace (Stage 13). The
        # recorder swallows its own errors, so this never affects the response.
        if self._recorder is not None and response.request_trace is not None:
            await self._recorder.record(response.request_trace)
        return response

    def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamEvent]:
        return self._runtime.stream(request)
