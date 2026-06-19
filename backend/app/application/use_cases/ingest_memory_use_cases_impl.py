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
from app.application.use_cases.memory_use_cases_impl import CreateMemoryUseCaseImpl

_logger = logging.getLogger("memoryarena.workflow")


class IngestMemoryUseCaseImpl(IngestMemoryUseCase):
    def __init__(
        self,
        engine: WorkflowEngine,
        uow_factory: Callable[[], UnitOfWork],
        dispatcher: EventDispatcher,
    ) -> None:
        self._engine = engine
        self._uow_factory = uow_factory
        self._dispatcher = dispatcher

    async def execute(self, request: ExtractionRequest) -> IngestSummary:
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
