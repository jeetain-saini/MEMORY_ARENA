"""AgentRuntime port — the query-time orchestration contract.

An ``AgentRuntime`` turns an ``AgentRequest`` into an ``AgentResponse`` by
orchestrating existing MemoryArena services (retrieval, graph expansion, context
assembly, compression, generation) — it owns no retrieval/assembly logic of its
own. Implementations live in ``infrastructure/llm/graphs`` and are selected by
configuration (sequential offline default; LangGraph in production). No LangGraph
type ever crosses this boundary: both methods take and yield plain DTOs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.application.dto.agent_dto import AgentRequest, AgentResponse, AgentStreamEvent


class AgentRuntime(ABC):
    @abstractmethod
    async def respond(self, request: AgentRequest) -> AgentResponse:
        """Run the agent to completion and return the full response."""

    @abstractmethod
    def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamEvent]:
        """Run the agent, yielding events as each stage completes.

        Implemented as an async generator. Must always yield a terminal
        ``done`` event (and an ``error`` event before it on failure), so a
        consumer can rely on a well-formed event stream even on timeout or
        cancellation.
        """
