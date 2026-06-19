"""EmbeddingJobProcessor port — async background processing of embedding work.

Embedding generation is offloaded from the request/event path so it never
blocks the caller. Stage 6 ships an in-process async worker; the same port can
later be backed by Celery, RQ, or a Kafka consumer with no change to producers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class EmbeddingAction(str, Enum):
    UPSERT = "upsert"   # (re)generate and store the embedding for a memory
    DELETE = "delete"   # remove the embedding(s) for a memory


@dataclass(frozen=True)
class EmbeddingJob:
    action: EmbeddingAction
    memory_id: UUID


class EmbeddingJobProcessor(ABC):
    @abstractmethod
    async def submit(self, job: EmbeddingJob) -> None:
        """Enqueue a job for asynchronous processing."""
