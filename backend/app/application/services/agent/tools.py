"""Agent tools — thin adapters over existing MemoryArena services.

Each tool invokes one service and records the result on the shared
``AgentState``. They hold no orchestration and no business logic; the retrieval,
graph-expansion, and context-assembly logic all stay in the services they wrap.

Critically, retrieval happens **once**: ``MemorySearchTool`` runs hybrid
retrieval and stores the base hits; ``GraphExpansionTool`` *reuses* those hits
via ``GraphAwareRetrievalService.expand`` rather than retrieving again; and
``ContextBuilderTool`` feeds the combined candidate set into the builder through
its pre-retrieved path. No subsystem is bypassed and none is run twice.
"""

from __future__ import annotations

from app.application.dto.agent_dto import AgentState, AgentStepResult, AgentToolCall
from app.application.dto.context_dto import ContextRequest
from app.application.dto.retrieval_dto import (
    MemorySearchQuery,
    RetrievalFilters,
    RetrievedMemory,
    ScoreBreakdown,
)
from app.application.interfaces.agent_tool import AgentTool
from app.application.services.context.context_builder import ContextBuilderService
from app.application.services.graph.graph_aware_retrieval import GraphAwareRetrievalService
from app.application.services.retrieval.retrieval_service import MemoryRetrievalService


class MemorySearchTool(AgentTool):
    """Hybrid retrieval — the single retrieval in the whole run."""

    def __init__(self, retrieval_service: MemoryRetrievalService) -> None:
        self._service = retrieval_service

    @property
    def name(self) -> str:
        return "memory_search"

    async def run(self, state: AgentState) -> AgentStepResult:
        call = AgentToolCall(tool_name=self.name, arguments={"query": state.query})
        try:
            result = await self._service.search(
                MemorySearchQuery(
                    query=state.query,
                    user_id=state.user_id,
                    filters=RetrievalFilters(),
                    top_k=state.config.top_k,
                )
            )
        except Exception as exc:  # noqa: BLE001 — surface as a degradable failure
            return AgentStepResult(
                step="retrieve", ok=False, tool_call=call, error=str(exc)
            )

        state.retrieved = result
        for hit in result.results:
            if hit.memory_id not in state.provenance:
                state.provenance[hit.memory_id] = "hybrid"
                state.candidates.append(hit)
        return AgentStepResult(
            step="retrieve",
            ok=True,
            tool_call=call,
            summary=f"retrieved {len(result.results)} memories",
        )


class GraphExpansionTool(AgentTool):
    """Graph expansion that reuses the already-retrieved base hits."""

    def __init__(self, graph_aware_service: GraphAwareRetrievalService) -> None:
        self._service = graph_aware_service

    @property
    def name(self) -> str:
        return "graph_expansion"

    async def run(self, state: AgentState) -> AgentStepResult:
        call = AgentToolCall(tool_name=self.name, arguments={"query": state.query})
        if state.retrieved is None:
            return AgentStepResult(
                step="expand", ok=False, tool_call=call, error="no base retrieval to expand"
            )

        query = MemorySearchQuery(
            query=state.query,
            user_id=state.user_id,
            filters=RetrievalFilters(),
            top_k=state.config.top_k,
        )
        try:
            result = await self._service.expand(state.retrieved, query)
        except Exception as exc:  # noqa: BLE001
            return AgentStepResult(
                step="expand", ok=False, tool_call=call, error=str(exc)
            )

        state.expanded = result
        graph_added = 0
        for mem in result.results:
            if mem.provenance != "graph" or mem.memory_id in state.provenance:
                continue
            state.provenance[mem.memory_id] = "graph"
            state.candidates.append(_expanded_to_retrieved(mem, state))
            graph_added += 1
        return AgentStepResult(
            step="expand",
            ok=True,
            tool_call=call,
            summary=f"expanded {graph_added} graph neighbors",
        )


class ContextBuilderTool(AgentTool):
    """Context assembly — produces the primary ContextPackage artifact."""

    def __init__(self, context_builder: ContextBuilderService) -> None:
        self._builder = context_builder

    @property
    def name(self) -> str:
        return "context_builder"

    async def run(self, state: AgentState) -> AgentStepResult:
        call = AgentToolCall(tool_name=self.name, arguments={"max_tokens": state.config.max_tokens})
        request = ContextRequest(
            query=state.query,
            user_id=state.user_id,
            max_tokens=state.config.max_tokens,
            top_k=state.config.top_k,
            metadata=state.metadata,
        )
        try:
            package = await self._builder.build(request, retrieved=state.candidates)
        except Exception as exc:  # noqa: BLE001
            return AgentStepResult(
                step="build_context", ok=False, tool_call=call, error=str(exc)
            )

        state.context_package = package
        return AgentStepResult(
            step="build_context",
            ok=True,
            tool_call=call,
            summary=f"assembled context ({package.total_tokens} tokens)",
            tokens=package.total_tokens,
        )


def _expanded_to_retrieved(mem, state: AgentState) -> RetrievedMemory:
    """Map a graph ``ExpandedMemory`` to a ``RetrievedMemory`` for the builder."""
    return RetrievedMemory(
        memory_id=mem.memory_id,
        user_id=state.user_id,
        content=mem.content,
        memory_type=mem.memory_type,
        status=mem.status,
        final_score=mem.score,
        scores=ScoreBreakdown(
            vector_score=0.0,
            bm25_score=0.0,
            memory_score=0.0,
            recency_score=0.0,
            final_score=mem.score,
        ),
    )
