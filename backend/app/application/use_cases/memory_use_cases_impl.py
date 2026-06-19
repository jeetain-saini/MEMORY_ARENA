"""Concrete use-case implementations.

Each use case orchestrates the domain through the Unit of Work and repository
ports, enforces domain rules, and — after a successful commit — dispatches the
domain events the aggregate recorded. They depend only on abstractions
(``UnitOfWork``, ``EventDispatcher``), never on a concrete database or broker.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.memory_dto import (
    CreateMemoryRequest,
    CreateMemoryResponse,
    MemorySearchRequest,
    UpdateMemoryRequest,
)
from app.application.exceptions import MemoryNotFoundException, MemoryValidationException
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.presenters import memory_to_response
from app.application.use_cases.memory_use_cases import (
    CreateMemoryUseCase,
    DeleteMemoryUseCase,
    SearchMemoryUseCase,
    UpdateMemoryUseCase,
)
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.entities.memory_version import MemoryVersion


class CreateMemoryUseCaseImpl(CreateMemoryUseCase):
    def __init__(self, uow: UnitOfWork, dispatcher: EventDispatcher) -> None:
        self._uow = uow
        self._dispatcher = dispatcher

    async def execute(self, request: CreateMemoryRequest) -> CreateMemoryResponse:
        memory = Memory.create(
            user_id=request.user_id,
            content=request.content,
            memory_type=request.memory_type,
            metadata=request.metadata,
            score=_initial_score(request),
        )
        async with self._uow as uow:
            await uow.memories.save(memory)
            await uow.commit()
        await self._dispatcher.dispatch(memory.pull_events())
        return memory_to_response(memory)


class UpdateMemoryUseCaseImpl(UpdateMemoryUseCase):
    def __init__(self, uow: UnitOfWork, dispatcher: EventDispatcher) -> None:
        self._uow = uow
        self._dispatcher = dispatcher

    async def execute(self, request: UpdateMemoryRequest) -> CreateMemoryResponse:
        if request.content is None and request.metadata is None:
            raise MemoryValidationException("Nothing to update: provide content and/or metadata.")

        async with self._uow as uow:
            memory = await uow.memories.get_by_id(request.memory_id)
            if memory is None or memory.user_id != request.user_id:
                raise MemoryNotFoundException(request.memory_id)

            # Snapshot the pre-edit state for history/rollback BEFORE mutating.
            await uow.versions.save(MemoryVersion.capture(memory, reason=request.reason))

            new_content = request.content if request.content is not None else memory.content
            memory.update_content(new_content, metadata=request.metadata, reason=request.reason)

            updated = await uow.memories.update(memory)
            await uow.commit()

        await self._dispatcher.dispatch(memory.pull_events())
        return memory_to_response(updated)


class DeleteMemoryUseCaseImpl(DeleteMemoryUseCase):
    def __init__(self, uow: UnitOfWork, dispatcher: EventDispatcher) -> None:
        self._uow = uow
        self._dispatcher = dispatcher

    async def execute(self, *, memory_id: UUID, user_id: UUID) -> None:
        async with self._uow as uow:
            memory = await uow.memories.get_by_id(memory_id)
            if memory is None or memory.user_id != user_id:
                raise MemoryNotFoundException(memory_id)

            memory.delete()  # domain transition -> records MemoryDeleted
            await uow.memories.delete(memory_id)  # soft-delete in the store
            await uow.commit()

        await self._dispatcher.dispatch(memory.pull_events())


class SearchMemoryUseCaseImpl(SearchMemoryUseCase):
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, request: MemorySearchRequest) -> list[CreateMemoryResponse]:
        async with self._uow as uow:
            memories = await uow.memories.search(request)
        return [memory_to_response(m) for m in memories]


def _initial_score(request: CreateMemoryRequest) -> MemoryScore | None:
    """Seed a score from optional importance/confidence signals.

    Returns ``None`` (→ ``MemoryScore.neutral()``) when neither is supplied, so
    the default create behavior is unchanged. Unsupplied components fall back to
    the neutral defaults on ``MemoryScore``.
    """
    if request.importance is None and request.confidence is None:
        return None
    neutral = MemoryScore.neutral()
    return MemoryScore(
        importance=request.importance if request.importance is not None else neutral.importance,
        confidence=request.confidence if request.confidence is not None else neutral.confidence,
    )
