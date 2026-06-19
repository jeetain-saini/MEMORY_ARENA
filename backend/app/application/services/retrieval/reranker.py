"""SimpleCrossEncoderReranker — lightweight heuristic reranking.

A dependency-free stand-in for a learned cross-encoder. It nudges the fused
score by the lexical overlap between the query and each candidate's content:

    rerank = final · (1 + overlap_weight · |query∩doc| / |query|)

Deterministic and fast — good enough to reorder near-ties. Swap in a real
cross-encoder / Cohere / BGE reranker later behind the ``Reranker`` port.
"""

from __future__ import annotations

from dataclasses import replace

from app.application.dto.retrieval_dto import RetrievedMemory
from app.application.interfaces.reranker import Reranker
from app.application.services.retrieval.bm25 import tokenize


class SimpleCrossEncoderReranker(Reranker):
    def __init__(self, overlap_weight: float = 0.25) -> None:
        self._overlap_weight = overlap_weight

    def rerank(self, query: str, candidates: list[RetrievedMemory]) -> list[RetrievedMemory]:
        query_terms = set(tokenize(query))
        if not query_terms or not candidates:
            return list(candidates)

        reranked: list[RetrievedMemory] = []
        for candidate in candidates:
            doc_terms = set(tokenize(candidate.content))
            overlap = len(query_terms & doc_terms) / len(query_terms)
            new_score = round(candidate.final_score * (1 + self._overlap_weight * overlap), 6)
            reranked.append(
                replace(
                    candidate,
                    final_score=new_score,
                    scores=replace(candidate.scores, final_score=new_score),
                )
            )

        reranked.sort(key=lambda r: r.final_score, reverse=True)
        return reranked
