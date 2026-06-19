"""ConflictDetector — find contradicting memories.

Heuristic (no LLM): two memories contradict when they talk about the same thing
(high overlap of *significant* terms) but exactly one of them is negated. This
catches cases like:

    "I use Python"   vs   "I no longer use Python"

Significant terms exclude stopwords and negation markers, so the overlap
measures the shared subject while the negation XOR detects the disagreement.
"""

from __future__ import annotations

from itertools import combinations

from app.application.dto.context_dto import ConflictRecord, ContextMemory
from app.application.services.context._text import jaccard
from app.application.services.retrieval.bm25 import tokenize

NEGATION_MARKERS = frozenset(
    {
        "no", "not", "never", "none", "stopped", "stop", "quit", "former",
        "formerly", "longer", "dont", "doesnt", "didnt", "isnt", "wasnt",
        "arent", "cannot", "cant", "without", "ex", "neither", "nor",
    }
)

STOPWORDS = frozenset(
    {
        "i", "you", "he", "she", "we", "they", "it", "the", "a", "an", "is",
        "am", "are", "was", "were", "be", "been", "to", "of", "and", "or",
        "my", "your", "his", "her", "our", "their", "this", "that", "these",
        "those", "do", "does", "did", "have", "has", "had", "for", "in", "on",
        "at", "with", "as",
    }
)


class ConflictDetector:
    def __init__(self, threshold: float = 0.6) -> None:
        self._threshold = threshold

    def detect(self, memories: list[ContextMemory]) -> list[ConflictRecord]:
        analyzed = [(m, self._analyze(m.content)) for m in memories]
        conflicts: list[ConflictRecord] = []

        for (mem_a, (sig_a, neg_a)), (mem_b, (sig_b, neg_b)) in combinations(analyzed, 2):
            if not sig_a or not sig_b:
                continue
            if neg_a == neg_b:
                continue  # need exactly one negation to contradict
            if jaccard(sig_a, sig_b) >= self._threshold:
                conflicts.append(
                    ConflictRecord(
                        memory_id_a=mem_a.memory_id,
                        memory_id_b=mem_b.memory_id,
                        reason="negation_contradiction",
                        content_a=mem_a.content,
                        content_b=mem_b.content,
                    )
                )
        return conflicts

    @staticmethod
    def _analyze(content: str) -> tuple[set[str], bool]:
        tokens = tokenize(content)
        negated = any(token in NEGATION_MARKERS for token in tokens)
        significant = {
            token
            for token in tokens
            if token not in STOPWORDS and token not in NEGATION_MARKERS
        }
        return significant, negated
