"""Intelligence job processor port (Stage 17.1).

Carries an ``IntelligenceJob`` (a request to re-evaluate a user's memories for
promotion + clustering after a new memory was created) to a background
processor, mirroring the embedding / graph / maintenance processors. The
application depends on this abstraction; the in-process implementation lives in
``infrastructure``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class IntelligenceJob:
    user_id: UUID


class IntelligenceJobProcessor(ABC):
    @abstractmethod
    async def submit(self, job: IntelligenceJob) -> None:
        """Enqueue an intelligence re-evaluation job for background execution."""
