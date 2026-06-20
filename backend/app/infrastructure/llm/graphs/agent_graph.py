"""LangGraphAgentRuntime — production query-time agent via a StateGraph.

Wires the shared agent node functions (``agent_steps``) as nodes of a linear
``StateGraph``. The per-node logic — including every guardrail — is the exact
same code the sequential runtime runs, so the two never diverge and the graph is
future-compatible with tool loops (add a conditional edge later).

``langgraph`` is imported lazily (inside ``__init__``) so this module imports
cleanly without the package; the offline default runtime is sequential, and the
LangGraph suite ``importorskip('langgraph')``. No LangGraph type escapes this
class: ``respond``/``stream`` take and yield plain DTOs.

Guards present now: ``max_iterations`` and ``max_tool_calls`` (in the shared
nodes), ``token`` (context budget + answer cap), and ``timeout`` (wrapping the
graph invocation / the stream).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.application.dto.agent_dto import (
    FINISH_TIMEOUT,
    AgentRequest,
    AgentResponse,
    AgentState,
    AgentStreamEvent,
)
from app.application.interfaces.agent_runtime import AgentRuntime
from app.application.interfaces.clock import Clock
from app.application.interfaces.llm_provider import LLMProvider
from app.application.interfaces.token_counter import TokenCounter
from app.application.services.agent.toolset import AgentToolSet
from app.infrastructure.llm.graphs import agent_steps


class LangGraphAgentRuntime(AgentRuntime):
    def __init__(
        self,
        toolset: AgentToolSet,
        provider: LLMProvider,
        token_counter: TokenCounter,
        clock: Clock | None = None,
    ) -> None:
        from langgraph.graph import END, START, StateGraph  # lazy import

        self._toolset = toolset
        self._provider = provider
        self._counter = token_counter
        self._clock = clock

        builder: StateGraph = StateGraph(AgentState)
        builder.add_node("retrieve", self._node(lambda s: agent_steps.node_retrieve(s, toolset)))
        builder.add_node("expand", self._node(lambda s: agent_steps.node_expand(s, toolset)))
        builder.add_node("build_context", self._node(lambda s: agent_steps.node_build(s, toolset)))
        builder.add_node(
            "generate",
            self._node(lambda s: agent_steps.node_generate(s, provider, token_counter)),
        )
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "expand")
        builder.add_edge("expand", "build_context")
        builder.add_edge("build_context", "generate")
        builder.add_edge("generate", END)
        self._graph = builder.compile()

    @staticmethod
    def _node(fn):
        async def node(state: AgentState) -> AgentState:
            return await fn(state)

        return node

    async def respond(self, request: AgentRequest) -> AgentResponse:
        import asyncio

        state = agent_steps.init_state(request, clock=self._clock)
        try:
            result = await asyncio.wait_for(
                self._graph.ainvoke(state), timeout=request.config.timeout_seconds
            )
            final = result if isinstance(result, AgentState) else state
        except asyncio.TimeoutError:
            final = state
            final.finish_reason = FINISH_TIMEOUT
            final.terminated = True
        agent_steps._finalize_citations(final)
        return agent_steps.to_response(final)

    async def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamEvent]:
        # Streaming reuses the shared event generator (the graph is the respond
        # path; per-node astream can be added when tool loops land).
        state = agent_steps.init_state(request, clock=self._clock)
        async for event in agent_steps.stream_with_timeout(
            state, self._toolset, self._provider, self._counter, request.config.timeout_seconds
        ):
            yield event
