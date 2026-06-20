"""SequentialConsolidationEngine — offline default consolidation engine.

Runs the four shared consolidation steps in order with no LangGraph dependency.
This is the dev/test default, so the consolidation pipeline works without API
keys or optional packages.  The production LangGraphConsolidationEngine wires
the same steps into a StateGraph.
"""

from __future__ import annotations

from app.application.dto.consolidation_dto import ConsolidationDecision, ConsolidationRequest
from app.application.interfaces.consolidation_engine import ConsolidationEngine
from app.application.interfaces.llm_provider import LLMProvider
from app.infrastructure.llm.graphs.consolidation_steps import (
    STEPS,
    ConsolidationState,
)


class SequentialConsolidationEngine(ConsolidationEngine):
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def consolidate(self, request: ConsolidationRequest) -> list[ConsolidationDecision]:
        state = ConsolidationState(
            new_memory_id=request.new_memory_id,
            new_content=request.new_content,
            candidates=list(request.candidates),
        )
        for step in STEPS:
            state = step(state, self._provider)
        return state.decisions
