"""ContextBuilderService — the Context Assembly pipeline.

    retrieval -> selection -> consolidation -> conflict detection -> compression -> ContextPackage

``build`` returns the assembled package; ``debug`` returns the package plus full
provenance: which memories were selected, which were dropped (and why),
contradictions found, duplicate consolidations, and compression stats.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.context_dto import (
    CompressionStats,
    ConflictRecord,
    ConsolidationRecord,
    ContextDebugPackage,
    ContextMemory,
    ContextPackage,
    ContextRequest,
    DroppedMemory,
)
from app.application.dto.retrieval_dto import MemorySearchQuery
from app.application.interfaces.context_compressor import ContextCompressor
from app.application.services.context.conflict_detector import ConflictDetector
from app.application.services.context.consolidation_service import MemoryConsolidationService
from app.application.services.context.selection_service import MemorySelectionService
from app.application.services.retrieval.retrieval_service import MemoryRetrievalService


@dataclass
class _Assembly:
    package: ContextPackage
    selected: list[ContextMemory]
    dropped: list[DroppedMemory]
    conflicts: list[ConflictRecord]
    consolidations: list[ConsolidationRecord]
    compression: CompressionStats


class ContextBuilderService:
    def __init__(
        self,
        retrieval_service: MemoryRetrievalService,
        selection_service: MemorySelectionService,
        consolidation_service: MemoryConsolidationService,
        conflict_detector: ConflictDetector,
        compressor: ContextCompressor,
    ) -> None:
        self._retrieval = retrieval_service
        self._selection = selection_service
        self._consolidation = consolidation_service
        self._conflicts = conflict_detector
        self._compressor = compressor

    async def build(self, request: ContextRequest) -> ContextPackage:
        return (await self._assemble(request)).package

    async def debug(self, request: ContextRequest) -> ContextDebugPackage:
        a = await self._assemble(request)
        return ContextDebugPackage(
            package=a.package,
            selected=a.selected,
            dropped=a.dropped,
            conflicts=a.conflicts,
            consolidations=a.consolidations,
            compression=a.compression,
        )

    async def _assemble(self, request: ContextRequest) -> _Assembly:
        retrieval = await self._retrieval.search(
            MemorySearchQuery(
                query=request.query,
                user_id=request.user_id,
                filters=request.filters,
                top_k=request.top_k,
            )
        )

        selection = self._selection.select(retrieval.results, request.max_tokens)
        consolidation = self._consolidation.consolidate(selection.selected)
        conflicts = self._conflicts.detect(consolidation.consolidated)
        compression = await self._compressor.compress(
            consolidation.consolidated, request.max_tokens
        )

        package = ContextPackage(
            query=request.query,
            user_id=request.user_id,
            memories=compression.memories,
            context_text=compression.context_text,
            total_tokens=compression.stats.compressed_tokens,
            max_tokens=request.max_tokens,
            metadata=request.metadata,
        )
        dropped = selection.dropped + consolidation.removed + compression.removed
        return _Assembly(
            package=package,
            selected=compression.memories,
            dropped=dropped,
            conflicts=conflicts,
            consolidations=consolidation.records,
            compression=compression.stats,
        )
