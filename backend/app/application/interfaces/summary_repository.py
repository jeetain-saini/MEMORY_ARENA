"""MemorySummaryRepository port — persistence for rolling memory summaries.

One summary per ``(user_id, scope)``; the summarization workflow upserts it. Kept
separate from the memory repositories because summaries are derived artifacts, not
part of the Memory aggregate.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.memory_summary import MemorySummary
from app.domain.value_objects.memory_type import MemoryType


class MemorySummaryRepository(ABC):
    @abstractmethod
    async def upsert(self, summary: MemorySummary) -> MemorySummary:
        """Insert or update the summary for its ``(user_id, scope)``."""

    @abstractmethod
    async def get(self, user_id: UUID, scope: MemoryType) -> MemorySummary | None: ...

    @abstractmethod
    async def list_for_user(self, user_id: UUID) -> list[MemorySummary]: ...

    @abstractmethod
    async def delete(self, user_id: UUID, scope: MemoryType) -> None: ...
