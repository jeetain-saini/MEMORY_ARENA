"""QueryMemoryUseCaseImpl — delegates to the AgentRuntime port.

Thin orchestration: it owns no retrieval/assembly/generation logic and no
infrastructure handles — it forwards to the injected ``AgentRuntime`` (selected
by configuration at the composition root) and returns plain DTOs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.application.dto.agent_dto import AgentRequest, AgentResponse, AgentStreamEvent
from app.application.interfaces.agent_runtime import AgentRuntime
from app.application.use_cases.query_memory_use_cases import QueryMemoryUseCase


class QueryMemoryUseCaseImpl(QueryMemoryUseCase):
    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    async def execute(self, request: AgentRequest) -> AgentResponse:
        return await self._runtime.respond(request)

    def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamEvent]:
        return self._runtime.stream(request)
