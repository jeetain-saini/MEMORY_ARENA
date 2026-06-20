"""LangGraphConsolidationEngine — production consolidation engine.

Wires the four shared consolidation steps into a LangGraph StateGraph.  The
only structural difference from SequentialConsolidationEngine is the conditional
edge after score_candidates: when no candidates pass the threshold
(state.short_circuit is True) the graph jumps directly to validate_decisions,
skipping classify_pairs and enrich_reasoning.

LangGraph is a lazy import so the package is optional; tests skip when it is
not installed (pytest.importorskip("langgraph")).
"""

from __future__ import annotations

from app.application.dto.consolidation_dto import ConsolidationDecision, ConsolidationRequest
from app.application.interfaces.consolidation_engine import ConsolidationEngine
from app.application.interfaces.llm_provider import LLMProvider
from app.infrastructure.llm.graphs.consolidation_steps import (
    ConsolidationState,
    classify_pairs,
    enrich_reasoning,
    score_candidates,
    validate_decisions,
)


class LangGraphConsolidationEngine(ConsolidationEngine):
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self._graph = self._build_graph()

    def _build_graph(self):  # type: ignore[no-untyped-def]
        from langgraph.graph import END, START, StateGraph  # type: ignore[import]

        p = self._provider

        def _score(state: ConsolidationState) -> ConsolidationState:
            return score_candidates(state, p)

        def _classify(state: ConsolidationState) -> ConsolidationState:
            return classify_pairs(state, p)

        def _enrich(state: ConsolidationState) -> ConsolidationState:
            return enrich_reasoning(state, p)

        def _validate(state: ConsolidationState) -> ConsolidationState:
            return validate_decisions(state, p)

        def _route_after_score(state: ConsolidationState) -> str:
            return "validate" if state.short_circuit else "classify"

        graph = StateGraph(ConsolidationState)
        graph.add_node("score", _score)
        graph.add_node("classify", _classify)
        graph.add_node("enrich", _enrich)
        graph.add_node("validate", _validate)

        graph.add_edge(START, "score")
        graph.add_conditional_edges("score", _route_after_score, {"classify": "classify", "validate": "validate"})
        graph.add_edge("classify", "enrich")
        graph.add_edge("enrich", "validate")
        graph.add_edge("validate", END)

        return graph.compile()

    async def consolidate(self, request: ConsolidationRequest) -> list[ConsolidationDecision]:
        state = ConsolidationState(
            new_memory_id=request.new_memory_id,
            new_content=request.new_content,
            candidates=list(request.candidates),
        )
        result = await self._graph.ainvoke(state)
        return result.decisions if hasattr(result, "decisions") else result.get("decisions", [])
