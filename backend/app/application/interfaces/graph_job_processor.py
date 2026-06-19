"""GraphJobProcessor port — async background processing of graph-sync work.

Knowledge-graph synchronization is offloaded from the request/event path so it
never blocks the caller (mirroring the Stage 6 embedding pipeline). Stage 9
ships an in-process async worker; the same port can later be backed by Celery,
RQ, or a Kafka consumer with no change to producers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class GraphSyncAction(str, Enum):
    SYNC = "sync"      # upsert the memory's node and (re)derive its edges
    REMOVE = "remove"  # remove the memory's node (and its incident edges)


@dataclass(frozen=True)
class GraphSyncJob:
    action: GraphSyncAction
    memory_id: UUID


class GraphJobProcessor(ABC):
    @abstractmethod
    async def submit(self, job: GraphSyncJob) -> None:
        """Enqueue a job for asynchronous processing."""
