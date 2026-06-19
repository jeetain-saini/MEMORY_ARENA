"""Extraction DTOs — the contract between the LangGraph workflow and the app.

Plain dataclasses (no pydantic, no LangChain/LangGraph). The workflow engine
returns these; the ingest use case maps each ``ExtractedMemory`` onto a
``CreateMemoryRequest`` so memories enter through the single write path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.domain.value_objects.memory_type import MemoryType


@dataclass(frozen=True)
class ExtractionRequest:
    """Raw signal to extract memories from."""

    user_id: UUID
    raw_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractedMemory:
    """One memory candidate produced by the extraction workflow.

    ``importance`` and ``confidence`` are normalized [0,1] estimates that flow
    into the created memory's ``MemoryScore`` via ``CreateMemoryRequest``.
    """

    content: str
    memory_type: MemoryType
    importance: float
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    """The output of a workflow run.

    ``workflow_version`` identifies the workflow generation that produced these
    memories so future generations can be traced and compared (Decision C).
    """

    memories: list[ExtractedMemory]
    workflow_version: str
    source_chars: int = 0


@dataclass(frozen=True)
class IngestSummary:
    """Result of ingesting raw text: what the workflow produced and persisted."""

    user_id: UUID
    extracted_count: int
    created_ids: list[UUID]
    workflow_version: str
