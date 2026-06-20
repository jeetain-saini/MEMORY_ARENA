"""Maintenance job processor port (Stage 11 Phase B).

Carries an ``InferenceJob`` (a request to infer relationships for a newly created
memory) to a background processor, mirroring the embedding / graph / workflow /
consolidation processors. The application depends on this abstraction; the
in-process implementation lives in ``infrastructure``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class InferenceJob:
    memory_id: UUID
    user_id: UUID


class MaintenanceJobProcessor(ABC):
    @abstractmethod
    async def submit(self, job: InferenceJob) -> None:
        """Enqueue a relationship-inference job for background execution."""
