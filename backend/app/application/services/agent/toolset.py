"""AgentToolSet — the agent's enumerable capability surface.

Aggregates the concrete tools and exposes them by name. The runtime sequences
tools through this set; adding a future tool (e.g. a write tool) is a matter of
registering it here, with no change to the runtime contract.
"""

from __future__ import annotations

from app.application.interfaces.agent_tool import AgentTool
from app.application.services.agent.tools import (
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)


class AgentToolSet:
    def __init__(
        self,
        search: MemorySearchTool,
        expansion: GraphExpansionTool,
        context: ContextBuilderTool,
    ) -> None:
        self.search = search
        self.expansion = expansion
        self.context = context
        self._by_name: dict[str, AgentTool] = {
            search.name: search,
            expansion.name: expansion,
            context.name: context,
        }

    def get(self, name: str) -> AgentTool:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def names(self) -> list[str]:
        return list(self._by_name)

    def __len__(self) -> int:
        return len(self._by_name)
