"""SequentialExtractionEngine — the offline default extraction engine.

Runs the shared extraction steps in order, with no LangGraph dependency. This
is the dev/test default (mirroring the hash embedding provider and in-memory
graph backend), so the full ingestion pipeline runs offline. The production
``LangGraphExtractionEngine`` wires the same steps into a StateGraph.
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


class SequentialExtractionEngine(WorkflowEngine):
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def extract_memories(self, request: ExtractionRequest) -> ExtractionResult:
        state = ExtractionState(raw_text=request.raw_text)
        for step in STEPS:
            state = await step(state, self._provider)
        return ExtractionResult(
            memories=state.memories,
            workflow_version=WORKFLOW_VERSION,
            source_chars=len(request.raw_text),
        )
