"""Ingest use-case contract — raw text in, persisted memories out.

The write-path entry point for Stage 10: run the extraction workflow, then
create each extracted memory through the existing ``CreateMemoryUseCase`` so the
domain-event pipeline (embeddings + graph sync) fires unchanged. This is a
contract only; the implementation depends on the workflow + UoW + dispatcher
abstractions, never on LangGraph or a concrete store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.extraction_dto import ExtractionRequest, IngestSummary
from app.application.interfaces.workflow_job_processor import WorkflowJob


class IngestMemoryUseCase(ABC):
    @abstractmethod
    async def execute(self, request: ExtractionRequest) -> IngestSummary:
        """Extract memories from raw text and persist them via the write path."""

    @abstractmethod
    async def process(self, job: WorkflowJob) -> None:
        """Background entry point: run ``execute`` for a queued job."""
