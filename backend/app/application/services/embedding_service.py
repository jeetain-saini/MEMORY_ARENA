"""EmbeddingService — generate, store, update, and delete memory embeddings.

Orchestrates the embedding provider and the embedding repository. Unlike
request-scoped services, this one is app-scoped (driven by background jobs), so
it is given a Unit-of-Work *factory* and creates a fresh transaction per
operation — safe for concurrent jobs.

It performs no retrieval or similarity search; Stage 6 is generation + storage.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.dto.embedding_dto import EmbeddingRecord
from app.application.interfaces.embedding_job_processor import EmbeddingAction, EmbeddingJob
from app.application.interfaces.embedding_provider import EmbeddingProvider
from app.application.interfaces.unit_of_work import UnitOfWork
from app.domain.entities.memory import Memory


class EmbeddingService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        provider: EmbeddingProvider,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = provider

    # -- spec API (operate on a Memory) ------------------------------------
    async def generate_embedding(self, memory: Memory) -> list[float]:
        """Produce a vector for the memory's content (no persistence)."""
        return await self._provider.embed_text(memory.content)

    async def store_embedding(self, memory: Memory) -> EmbeddingRecord:
        record = await self._build_record(memory)
        async with self._uow_factory() as uow:
            await uow.embeddings.save_embedding(record)
            await uow.commit()
        return record

    async def update_embedding(self, memory: Memory) -> EmbeddingRecord:
        record = await self._build_record(memory)
        async with self._uow_factory() as uow:
            await uow.embeddings.update_embedding(record)
            await uow.commit()
        return record

    async def delete_embedding(self, memory: Memory) -> None:
        await self._delete(memory.id)

    # -- job API (operate on a memory_id; used by the background processor) -
    async def process(self, job: EmbeddingJob) -> None:
        if job.action is EmbeddingAction.DELETE:
            await self._delete(job.memory_id)
        else:
            await self._upsert(job.memory_id)

    async def _upsert(self, memory_id: UUID) -> None:
        async with self._uow_factory() as uow:
            memory = await uow.memories.get_by_id(memory_id)
            if memory is None:
                return  # memory gone (e.g. deleted) — nothing to embed
            record = await self._build_record(memory)
            await uow.embeddings.save_embedding(record)
            await uow.commit()

    async def _delete(self, memory_id: UUID) -> None:
        async with self._uow_factory() as uow:
            await uow.embeddings.delete_embedding(memory_id)
            await uow.commit()

    async def _build_record(self, memory: Memory) -> EmbeddingRecord:
        vector = await self._provider.embed_text(memory.content)
        return EmbeddingRecord(
            memory_id=memory.id,
            vector=vector,
            model_name=self._provider.model_name,
            dimensions=self._provider.dimensions,
        )
