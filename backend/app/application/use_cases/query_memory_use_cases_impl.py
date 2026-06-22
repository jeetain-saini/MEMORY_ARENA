"""QueryMemoryUseCaseImpl — delegates to the AgentRuntime port.

Thin orchestration: it owns no retrieval/assembly/generation logic and no
infrastructure handles — it forwards to the injected ``AgentRuntime`` (selected
by configuration at the composition root) and returns plain DTOs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.application.dto.agent_dto import AgentRequest, AgentResponse, AgentStreamEvent
from app.application.dto.auth_dto import AuthPrincipal
from app.application.interfaces.agent_runtime import AgentRuntime
from app.application.interfaces.trace_recorder import TraceRecorder
from app.application.services.agent.conversation_capture_service import (
    ConversationCaptureService,
)
from app.application.services.authorization import resolve_scope
from app.application.use_cases.query_memory_use_cases import QueryMemoryUseCase


class QueryMemoryUseCaseImpl(QueryMemoryUseCase):
    def __init__(
        self,
        runtime: AgentRuntime,
        trace_recorder: TraceRecorder | None = None,
        principal: AuthPrincipal | None = None,
        capture: ConversationCaptureService | None = None,
    ) -> None:
        self._runtime = runtime
        self._recorder = trace_recorder
        self._principal = principal
        self._capture = capture

    async def execute(self, request: AgentRequest) -> AgentResponse:
        resolve_scope(self._principal, request.user_id)
        response = await self._runtime.respond(request)
        # Best-effort observability: record the request trace (Stage 13). The
        # recorder swallows its own errors, so this never affects the response.
        if self._recorder is not None and response.request_trace is not None:
            await self._recorder.record(response.request_trace)
        # Conversational memory capture (Stage 15): off-path, failure-isolated;
        # a no-op unless enabled and the policy accepts the user's turn.
        if self._capture is not None:
            await self._capture.maybe_capture(request.user_id, request.query)
        return response

    def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamEvent]:
        # Synchronous scope check so an unauthorized stream fails before the SSE
        # body begins (the route also pre-checks for a clean 403 status).
        resolve_scope(self._principal, request.user_id)
        # Fire-and-forget capture (the user turn is known up front); isolated.
        if self._capture is not None:
            self._capture.schedule(request.user_id, request.query)
        return self._runtime.stream(request)
