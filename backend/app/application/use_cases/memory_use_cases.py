"""Use-case interfaces (application business-rule contracts).

Each use case is one unit of intent, expressed as an abstract ``execute``
method. These are contracts only — Stage 2 defines *what* the application can
do, not *how*. Concrete implementations (Stage 3) will depend on the repository
ports in ``application.interfaces`` and orchestrate domain entities.

Defined as ABCs so implementations are explicit and substitutable; the API
layer depends on these abstractions, never on a concrete class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.memory_dto import (
    CreateMemoryRequest,
    CreateMemoryResponse,
    MemorySearchRequest,
    UpdateMemoryRequest,
)


class CreateMemoryUseCase(ABC):
    """Create a new memory for a user."""

    @abstractmethod
    async def execute(self, request: CreateMemoryRequest) -> CreateMemoryResponse: ...


class UpdateMemoryUseCase(ABC):
    """Edit an existing memory, capturing a version snapshot beforehand."""

    @abstractmethod
    async def execute(self, request: UpdateMemoryRequest) -> CreateMemoryResponse: ...


class DeleteMemoryUseCase(ABC):
    """Tombstone a memory the user owns."""

    @abstractmethod
    async def execute(self, *, memory_id: UUID, user_id: UUID) -> None: ...


class SearchMemoryUseCase(ABC):
    """Search a user's memories by the given criteria."""

    @abstractmethod
    async def execute(self, request: MemorySearchRequest) -> list[CreateMemoryResponse]: ...
