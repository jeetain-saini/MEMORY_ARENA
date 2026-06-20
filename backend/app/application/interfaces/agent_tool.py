"""AgentTool port — a thin adapter over one existing MemoryArena service.

Tools are how the agent reaches the system's capabilities. Each tool wraps a
single existing service and contains **no business logic** — it invokes the
service, mutates the shared ``AgentState``, and reports an ``AgentStepResult``.
This keeps retrieval/expansion/assembly logic in exactly one place (the
services) and makes the agent's capability surface explicitly enumerable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.agent_dto import AgentState, AgentStepResult


class AgentTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def run(self, state: AgentState) -> AgentStepResult:
        """Invoke the wrapped service, update ``state``, return a step result.

        Implementations must not raise for an expected service failure —
        they catch it and return an ``AgentStepResult`` with ``ok=False`` and a
        populated ``error`` so the runtime can decide whether to degrade or
        terminate. (Programming errors may still surface.)
        """
