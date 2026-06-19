"""WorkflowEngine port — the extraction workflow behind an abstraction.

The ingest use case depends on this port and receives plain ``ExtractionResult``
DTOs. Concrete engines live in ``infrastructure/llm/graphs`` (a LangGraph
``StateGraph`` for production; a sequential engine for offline/dev). No
LangGraph/LangChain types ever cross this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.extraction_dto import ExtractionRequest, ExtractionResult


class WorkflowEngine(ABC):
    @abstractmethod
    async def extract_memories(self, request: ExtractionRequest) -> ExtractionResult:
        """Run the extraction workflow and return the extracted memories."""
