"""MemoryService — orchestration facade over the memory use cases.

The single entry point the API depends on for memory operations. It wires the
write/search use cases and provides the read paths (get-by-id, list-by-user)
through the Unit of Work. Orchestration only: it holds no persistence details
(those live behind the ports) and no HTTP details (those live in the routes).
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.memory_dto import (
    CreateMemoryRequest,
    CreateMemoryResponse,
    MemorySearchRequest,
    UpdateMemoryRequest,
)
from app.application.dto.auth_dto import AuthPrincipal
from app.application.exceptions import MemoryNotFoundException
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.presenters import memory_to_response
from app.application.services.authorization import authorize_owner, resolve_scope
from app.application.use_cases.memory_use_cases_impl import (
    CreateMemoryUseCaseImpl,
    DeleteMemoryUseCaseImpl,
    SearchMemoryUseCaseImpl,
    UpdateMemoryUseCaseImpl,
)


class MemoryService:
    def __init__(
        self,
        uow: UnitOfWork,
        dispatcher: EventDispatcher,
        principal: AuthPrincipal | None = None,
    ) -> None:
        self._uow = uow
        self._principal = principal
        self._create = CreateMemoryUseCaseImpl(uow, dispatcher)
        self._update = UpdateMemoryUseCaseImpl(uow, dispatcher)
        self._delete = DeleteMemoryUseCaseImpl(uow, dispatcher)
        self._search = SearchMemoryUseCaseImpl(uow)

    async def create(self, request: CreateMemoryRequest) -> CreateMemoryResponse:
        resolve_scope(self._principal, request.user_id)
        return await self._create.execute(request)

    async def update(self, request: UpdateMemoryRequest) -> CreateMemoryResponse:
        await self._require_owned(request.memory_id)
        return await self._update.execute(request)

    async def delete(self, *, memory_id: UUID, user_id: UUID) -> None:
        await self._require_owned(memory_id)
        await self._delete.execute(memory_id=memory_id, user_id=user_id)

    async def search(self, request: MemorySearchRequest) -> list[CreateMemoryResponse]:
        resolve_scope(self._principal, request.user_id)
        return await self._search.execute(request)

    async def get_by_id(self, memory_id: UUID) -> CreateMemoryResponse:
        async with self._uow as uow:
            memory = await uow.memories.get_by_id(memory_id)
        if memory is None:
            raise MemoryNotFoundException(memory_id)
        authorize_owner(self._principal, memory.user_id)
        return memory_to_response(memory)

    async def list_by_user(
        self, user_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[CreateMemoryResponse]:
        resolve_scope(self._principal, user_id)
        async with self._uow as uow:
            memories = await uow.memories.list_by_user(user_id, limit=limit, offset=offset)
        return [memory_to_response(m) for m in memories]

    async def _require_owned(self, memory_id: UUID) -> None:
        """Ownership guard for by-id mutations (no-op when auth is disabled)."""
        if self._principal is None:
            return
        async with self._uow as uow:
            memory = await uow.memories.get_by_id(memory_id)
        if memory is None:
            raise MemoryNotFoundException(memory_id)
        authorize_owner(self._principal, memory.user_id)
