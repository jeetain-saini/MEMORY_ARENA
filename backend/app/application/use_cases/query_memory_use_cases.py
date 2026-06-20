"""QueryMemoryUseCase port — the query-time entry point.

A single use case that invokes the ``AgentRuntime`` and returns its response. It
holds no infrastructure access of its own (no repositories, no SDKs); it only
orchestrates the runtime behind its port, keeping the API layer and the runtime
implementation decoupled.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.application.dto.agent_dto import AgentRequest, AgentResponse, AgentStreamEvent


class QueryMemoryUseCase(ABC):
    @abstractmethod
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Run the agent and return the full response."""

    @abstractmethod
    def stream(self, request: AgentRequest) -> AsyncIterator[AgentStreamEvent]:
        """Run the agent, yielding events for streaming delivery."""
