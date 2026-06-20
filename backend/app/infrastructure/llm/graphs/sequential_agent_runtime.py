"""SequentialAgentRuntime — offline default query-time agent.

Runs the shared agent stages in a single linear pass: retrieve -> expand ->
build context -> generate -> citations. No loops, no autonomous planning. The
timeout guard wraps the whole run; the max_iterations / max_tool_calls / token
guards live in the shared stage helpers. ``ContextPackage`` is the primary
artifact the answer is generated from.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.application.dto.agent_dto import (
    FINISH_TIMEOUT,
    AgentRequest,
    AgentResponse,
    AgentStreamEvent,
)
from app.application.interfaces.agent_runtime import AgentRuntime
from app.application.interfaces.clock import Clock
from app.application.interfaces.llm_provider import LLMProvider
from app.application.interfaces.token_counter import TokenCounter
from app.application.services.agent.toolset import AgentToolSet
from app.infrastructure.llm.graphs import agent_steps


class SequentialAgentRuntime(AgentRuntime):
    def __init__(
        self,
        toolset: AgentToolSet,
        provider: LLMProvider,
        token_counter: TokenCounter,
        clock: Clock | None = None,
    ) -> None:
        self._toolset = toolset
        self._provider = provider
        self._counter = token_counter
        self._clock = clock

    async def respond(self, request: AgentRequest) -> AgentResponse:
        state = agent_steps.init_state(request, clock=self._clock)
        try:
            await asyncio.wait_for(
                agent_steps.execute(state, self._toolset, self._provider, self._counter),
                timeout=request.config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            state.finish_reason = FINISH_TIMEOUT
            state.terminated = True
            agent_steps._finalize_citations(state)
        return agent_steps.to_response(state)

    async def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamEvent]:
        state = agent_steps.init_state(request, clock=self._clock)
        async for event in agent_steps.stream_with_timeout(
            state, self._toolset, self._provider, self._counter, request.config.timeout_seconds
        ):
            yield event
