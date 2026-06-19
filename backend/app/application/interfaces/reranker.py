"""Reranker port — reorders fused candidates for final relevance.

A second-stage ranker applied after fusion. Stage 7 ships a lightweight
heuristic; the same port can later be backed by a cross-encoder, Cohere Rerank,
or a BGE reranker with no change to the retrieval service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.retrieval_dto import RetrievedMemory


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: list[RetrievedMemory]) -> list[RetrievedMemory]:
        """Return candidates reordered (and possibly rescored) by relevance."""
