"""Citation validation — turn context memories into a trustworthy citation list.

The answer's citations are derived from the primary ``ContextPackage`` (and the
provenance recorded during retrieval/expansion). Before they are returned we:

  0. ground each memory in the generated ``answer`` (deterministic lexical
     containment): a memory is cited only if its significant terms actually
     appear in the answer, so retrieved-but-unused memories are dropped and a
     pure general-knowledge answer yields no citations
  1. deduplicate by ``memory_id`` (highest score wins)
  2. validate each ``memory_id`` against the set actually retrieved/expanded
     (a citation can never reference a memory the agent did not see)
  3. cap the count to ``max_citations`` (keep the highest-scored)
  4. preserve provenance (``hybrid`` vs ``graph``)

Pure, framework-free logic — no LLM, no I/O. Grounding is deterministic
(stopword-filtered token containment), so no second model pass is needed.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from app.application.dto.agent_dto import AgentCitation
from app.application.dto.context_dto import ContextMemory
from app.application.services.retrieval.bm25 import tokenize

# Common function words excluded from grounding so a citation is kept only when
# its *distinctive* terms appear in the answer (not incidental "the"/"is"/...).
_STOPWORDS = frozenset(
    {
        "i", "you", "he", "she", "we", "they", "it", "the", "a", "an", "is",
        "am", "are", "was", "were", "be", "been", "to", "of", "and", "or",
        "my", "your", "his", "her", "our", "their", "this", "that", "these",
        "those", "do", "does", "did", "have", "has", "had", "for", "in", "on",
        "at", "with", "as", "use", "uses", "used", "using",
    }
)


def _significant_tokens(text: str) -> set[str]:
    return {t for t in tokenize(text) if t not in _STOPWORDS}


def _containment(memory_tokens: set[str], answer_tokens: set[str]) -> float:
    """Fraction of the memory's significant tokens present in the answer."""
    if not memory_tokens:
        return 0.0
    return len(memory_tokens & answer_tokens) / len(memory_tokens)


def _ground(
    memories: Iterable[ContextMemory], answer: str | None, threshold: float
) -> list[ContextMemory]:
    if answer is None:
        return list(memories)  # legacy: grounding not requested
    answer_tokens = _significant_tokens(answer)
    if not answer_tokens:
        return []  # empty/blank/timeout answer -> nothing was used -> no citations
    return [
        m
        for m in memories
        if _containment(_significant_tokens(m.content), answer_tokens) >= threshold
    ]


def build_citations(
    memories: Iterable[ContextMemory],
    provenance: dict[UUID, str],
    known_ids: set[UUID],
    max_citations: int,
    *,
    answer: str | None = None,
    grounding_threshold: float = 0.3,
) -> list[AgentCitation]:
    by_id: dict[UUID, AgentCitation] = {}
    # 0. ground in the answer (no-op when answer is None -> legacy behavior).
    for memory in _ground(memories, answer, grounding_threshold):
        # 2. validate: drop anything not actually retrieved/expanded.
        if memory.memory_id not in known_ids:
            continue
        candidate = AgentCitation(
            memory_id=memory.memory_id,
            content=memory.content,
            memory_type=memory.memory_type,
            provenance=provenance.get(memory.memory_id, "hybrid"),
            score=memory.score,
        )
        # 1. deduplicate: keep the higher-scored entry for a repeated id.
        existing = by_id.get(memory.memory_id)
        if existing is None or candidate.score > existing.score:
            by_id[memory.memory_id] = candidate

    ordered = sorted(by_id.values(), key=lambda c: c.score, reverse=True)
    # 3. cap (max_citations < 0 means "no limit").
    if max_citations >= 0:
        ordered = ordered[:max_citations]
    return ordered
