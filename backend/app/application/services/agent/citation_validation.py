"""Citation validation — turn context memories into a trustworthy citation list.

The answer's citations are derived from the primary ``ContextPackage`` (and the
provenance recorded during retrieval/expansion). Before they are returned we:

  1. deduplicate by ``memory_id`` (highest score wins)
  2. validate each ``memory_id`` against the set actually retrieved/expanded
     (a citation can never reference a memory the agent did not see)
  3. cap the count to ``max_citations`` (keep the highest-scored)
  4. preserve provenance (``hybrid`` vs ``graph``)

Pure, framework-free logic — no LLM, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from app.application.dto.agent_dto import AgentCitation
from app.application.dto.context_dto import ContextMemory


def build_citations(
    memories: Iterable[ContextMemory],
    provenance: dict[UUID, str],
    known_ids: set[UUID],
    max_citations: int,
) -> list[AgentCitation]:
    by_id: dict[UUID, AgentCitation] = {}
    for memory in memories:
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
