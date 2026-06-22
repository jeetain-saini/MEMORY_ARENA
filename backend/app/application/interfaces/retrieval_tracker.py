"""RetrievalTracker port — records that retrieval returned given memories.

Lets MemoryRetrievalService note retrieval frequency without depending on a
unit of work or repository (preserving the retrieval pipeline's boundaries).
The default wiring is a no-op-safe, failure-isolated adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class RetrievalTracker(ABC):
    @abstractmethod
    async def record(self, memory_ids: list[UUID]) -> None:
        """Note that these memories were returned by retrieval. Never raises."""
