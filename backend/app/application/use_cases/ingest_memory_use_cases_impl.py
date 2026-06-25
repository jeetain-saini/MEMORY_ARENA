"""IngestMemoryUseCaseImpl — orchestrates extraction -> the single write path.

App-scoped (driven by background jobs), so it takes a Unit-of-Work *factory* and
creates a fresh transaction per memory (mirroring the embedding service). It
never touches repositories or the graph directly: every memory is created via
``CreateMemoryUseCase``, whose post-commit events drive embeddings and graph sync.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.application.dto.extraction_dto import ExtractionRequest, IngestSummary
from app.application.dto.memory_dto import CreateMemoryRequest
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.interfaces.workflow_engine import WorkflowEngine
from app.application.interfaces.workflow_job_processor import WorkflowJob
from app.application.use_cases.ingest_memory_use_cases import IngestMemoryUseCase
from app.application.services.inference.evidence import new_evidence
from app.application.services.inference.knowledge_inference import InferredKnowledge
from app.application.services.inference.knowledge_inference import infer as infer_knowledge
from app.application.services.inference.semantic_inference import SemanticKnowledgeInferenceService
from app.application.use_cases.memory_use_cases_impl import CreateMemoryUseCaseImpl

_logger = logging.getLogger("memoryarena.workflow")


def _request_with_inference(
    request: ExtractionRequest,
    inferred: InferredKnowledge | None,
    *,
    source_type: str = "deterministic",
) -> ExtractionRequest:
    """Rewrite the request to the inferred statement; pass through when None.

    Seeds the Phase C evidence record (first_seen, confidence/importance/reason
    history, ...) into metadata — append-only, no migration."""
    if inferred is None:
        return request
    message = request.raw_text
    return ExtractionRequest(
        user_id=request.user_id,
        raw_text=inferred.statement,
        metadata={
            **request.metadata,
            "reason_for_inference": inferred.reason,
            "inferred_type": inferred.memory_type.value,
            "inference_confidence": inferred.confidence,
            "inference_importance": inferred.importance,
            "inference_topic": inferred.topic,
            "progression_stage": inferred.progression_stage,
            "original_text": message,
            "evidence": new_evidence(
                message=message,
                confidence=inferred.confidence,
                importance=inferred.importance,
                reason=inferred.reason,
                source_type=source_type,
                topic=inferred.topic,
                progression_stage=inferred.progression_stage,
            ),
        },
    )


def _apply_inference(request: ExtractionRequest) -> ExtractionRequest:
    """Prepend the deterministic (Phase A) inference layer."""
    return _request_with_inference(request, infer_knowledge(request.raw_text))


class IngestMemoryUseCaseImpl(IngestMemoryUseCase):
    def __init__(
        self,
        engine: WorkflowEngine,
        uow_factory: Callable[[], UnitOfWork],
        dispatcher: EventDispatcher,
        inference_service: SemanticKnowledgeInferenceService | None = None,
    ) -> None:
        self._engine = engine
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher
        # Optional Phase B semantic engine. When absent we use the deterministic
        # Phase A layer directly (the semantic engine itself falls back to it).
        self._inference_service = inference_service

    async def execute(self, request: ExtractionRequest) -> IngestSummary:
        # Phase A/B — prepend the Knowledge Inference Layer. Durable turns
        # ("What is Rust?" -> "Interested in Rust") are rewritten to the inferred
        # statement (never the raw question) before extraction; inference
        # metadata travels along as evidence. Best-effort: any failure inside the
        # semantic engine falls back to deterministic rules, never raising.
        if self._inference_service is not None:
            inferred = await self._inference_service.infer(request.raw_text)
            request = _request_with_inference(request, inferred, source_type="semantic")
        else:
            request = _apply_inference(request)
        result = await self._engine.extract_memories(request)

        created_ids = []
        for memory in result.memories:
            create_request = CreateMemoryRequest(
                user_id=request.user_id,
                content=memory.content,
                memory_type=memory.memory_type,
                metadata={**request.metadata, **memory.metadata},
                importance=memory.importance,
                confidence=memory.confidence,
            )
            # Fresh UoW per create -> independent transaction + event dispatch,
            # going through the single write path (embeddings + graph follow).
            create = CreateMemoryUseCaseImpl(self._uow_factory(), self._dispatcher)
            response = await create.execute(create_request)
            created_ids.append(response.id)

        return IngestSummary(
            user_id=request.user_id,
            extracted_count=len(result.memories),
            created_ids=created_ids,
            workflow_version=result.workflow_version,
        )

    async def process(self, job: WorkflowJob) -> None:
        summary = await self.execute(
            ExtractionRequest(user_id=job.user_id, raw_text=job.raw_text, metadata=job.metadata)
        )
        _logger.info(
            "ingest.job.done",
            extra={
                "job_id": str(job.job_id),
                "extracted": summary.extracted_count,
                "workflow_version": summary.workflow_version,
            },
        )
