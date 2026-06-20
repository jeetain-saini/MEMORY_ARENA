"""Unit tests for citation validation (dedup, id validation, cap, provenance)."""

from __future__ import annotations

from uuid import uuid4

from app.application.dto.context_dto import ContextMemory
from app.application.services.agent.citation_validation import build_citations
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def _cm(content: str, score: float, mid=None, mtype=MemoryType.FACT) -> ContextMemory:
    return ContextMemory(
        memory_id=mid or uuid4(), content=content, memory_type=mtype,
        status=MemoryStatus.ACTIVE, score=score, tokens=4,
    )


def test_dedup_keeps_higher_score() -> None:
    mid = uuid4()
    low = _cm("a", 0.3, mid=mid)
    high = _cm("a", 0.9, mid=mid)
    cites = build_citations([low, high], {mid: "hybrid"}, {mid}, max_citations=10)
    assert len(cites) == 1
    assert cites[0].score == 0.9


def test_validate_drops_unknown_ids() -> None:
    known_id = uuid4()
    known = _cm("known", 0.8, mid=known_id)
    unknown = _cm("hallucinated", 0.9)
    cites = build_citations([known, unknown], {known_id: "hybrid"}, {known_id}, max_citations=10)
    assert [c.memory_id for c in cites] == [known_id]


def test_max_citations_cap_keeps_highest() -> None:
    mems = [_cm(f"m{i}", score=i / 10) for i in range(5)]
    known = {m.memory_id for m in mems}
    prov = {m.memory_id: "hybrid" for m in mems}
    cites = build_citations(mems, prov, known, max_citations=2)
    assert len(cites) == 2
    assert cites[0].score >= cites[1].score
    assert cites[0].score == 0.4


def test_provenance_preserved() -> None:
    h_id, g_id = uuid4(), uuid4()
    mems = [_cm("hybrid one", 0.9, mid=h_id), _cm("graph one", 0.4, mid=g_id)]
    prov = {h_id: "hybrid", g_id: "graph"}
    cites = build_citations(mems, prov, {h_id, g_id}, max_citations=10)
    by_id = {c.memory_id: c.provenance for c in cites}
    assert by_id[h_id] == "hybrid"
    assert by_id[g_id] == "graph"


def test_negative_max_means_no_limit() -> None:
    mems = [_cm(f"m{i}", score=i / 10) for i in range(5)]
    known = {m.memory_id for m in mems}
    prov = {m.memory_id: "hybrid" for m in mems}
    cites = build_citations(mems, prov, known, max_citations=-1)
    assert len(cites) == 5
