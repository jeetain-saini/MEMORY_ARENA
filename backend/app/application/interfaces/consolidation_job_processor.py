"""ConsolidationJobProcessor port — async background processing of consolidation work.

Mirrors GraphJobProcessor / WorkflowJobProcessor.  A job always means
"evaluate this newly-created memory against the user's corpus"; no action enum
is needed.  Infrastructure ships an in-process async worker; the port can later
be backed by Celery, RQ, or a queue without changing producers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ConsolidationJob:
    memory_id: UUID
    user_id: UUID


class ConsolidationJobProcessor(ABC):
    @abstractmethod
    async def submit(self, job: ConsolidationJob) -> None:
        """Enqueue a consolidation job for asynchronous processing."""
