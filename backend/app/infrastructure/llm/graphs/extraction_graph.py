"""LangGraphExtractionEngine — production extraction via a LangGraph StateGraph.

Wires the shared extraction steps (``extraction_steps.STEPS``) as nodes of a
linear ``StateGraph``. LangGraph gives us a typed, inspectable, retry-friendly
state machine; the per-node logic is the exact same code the sequential engine
runs, so the two never diverge.

``langgraph`` is imported lazily (inside ``__init__``) so this module imports
cleanly even when the package is not installed — the offline default engine is
sequential, and tests that exercise this engine ``importorskip('langgraph')``.
No LangGraph type escapes this class; ``extract_memories`` returns plain DTOs.
"""

from __future__ import annotations

from app.application.dto.extraction_dto import ExtractionRequest, ExtractionResult
from app.application.interfaces.llm_provider import LLMProvider
from app.application.interfaces.workflow_engine import WorkflowEngine
from app.infrastructure.llm.graphs.extraction_steps import (
    STEPS,
    WORKFLOW_VERSION,
    ExtractionState,
)


class LangGraphExtractionEngine(WorkflowEngine):
    def __init__(self, provider: LLMProvider) -> None:
        from langgraph.graph import END, START, StateGraph  # lazy import

        self._provider = provider

        builder: StateGraph = StateGraph(ExtractionState)
        previous = START
        for step in STEPS:
            name = step.__name__
            builder.add_node(name, self._as_node(step))
            builder.add_edge(previous, name)
            previous = name
        builder.add_edge(previous, END)
        self._graph = builder.compile()

    def _as_node(self, step):
        async def node(state: ExtractionState) -> ExtractionState:
            return await step(state, self._provider)

        return node

    async def extract_memories(self, request: ExtractionRequest) -> ExtractionResult:
        final = await self._graph.ainvoke(ExtractionState(raw_text=request.raw_text))
        # LangGraph may return the state object or a dict-like; normalize.
        memories = final["memories"] if isinstance(final, dict) else final.memories
        return ExtractionResult(
            memories=memories,
            workflow_version=WORKFLOW_VERSION,
            source_chars=len(request.raw_text),
        )
