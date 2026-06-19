"""WorkflowJobProcessor port — async background execution of ingestion jobs.

Memory extraction is LLM-bound and multi-step, so it runs off the request path
(mirroring the embedding and graph job processors). The API submits a job and
returns immediately; the processor runs the ingest use case in the background.
The same port can later be backed by Celery, RQ, or a Kafka consumer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class WorkflowJob:
    job_id: UUID
    user_id: UUID
    raw_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowJobProcessor(ABC):
    @abstractmethod
    async def submit(self, job: WorkflowJob) -> None:
        """Enqueue an ingestion job for asynchronous processing."""
