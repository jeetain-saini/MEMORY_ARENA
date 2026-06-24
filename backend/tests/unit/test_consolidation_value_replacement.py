"""Value-replacement contradiction: a new statement of a single-valued attribute
supersedes the older one even without negation or a length increase
("favorite language is Rust" -> "...is Go")."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.application.dto.consolidation_dto import (
    ConsolidationCandidate,
    ConsolidationDecisionType,
    ConsolidationRequest,
)
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.graphs.sequential_consolidation_engine import (
    SequentialConsolidationEngine,
)


def _candidate(content: str, mid=None):
    return ConsolidationCandidate(
        memory_id=mid or uuid4(), content=content, memory_type=MemoryType.PREFERENCE,
        total_score=0.5, updated_at=datetime.now(timezone.utc),
    )


def _consolidate(new_content: str, candidate: ConsolidationCandidate):
    eng = SequentialConsolidationEngine(provider=object())
    req = ConsolidationRequest(
        new_memory_id=uuid4(), user_id=uuid4(), new_content=new_content,
        new_type=MemoryType.PREFERENCE, candidates=[candidate],
    )
    return asyncio.run(eng.consolidate(req))


def test_changed_favorite_supersedes_old():
    rust = _candidate("My favorite language is Rust")
    decisions = _consolidate("My favorite language is Go", rust)
    sup = [d for d in decisions if d.decision_type is ConsolidationDecisionType.SUPERSEDES]
    assert len(sup) == 1
    assert sup[0].target_id == rust.memory_id          # the OLD memory is superseded
    assert sup[0].confidence >= 0.80                   # clears the apply threshold


def test_changed_favorite_supersedes_even_when_new_is_shorter():
    # "Go" is shorter than "Rust" — the old length-based rule would miss this.
    longer = _candidate("My favorite programming language is Rust")
    decisions = _consolidate("My favorite programming language is Go", longer)
    assert any(d.decision_type is ConsolidationDecisionType.SUPERSEDES for d in decisions)


def test_different_attributes_do_not_supersede():
    # Different single-valued attributes must NOT supersede each other.
    lang = _candidate("My favorite language is Rust")
    decisions = _consolidate("My favorite food is pizza", lang)
    assert all(d.decision_type is not ConsolidationDecisionType.SUPERSEDES for d in decisions)


def test_coexisting_likes_do_not_supersede():
    # You can like both — must stay unique (only 2 shared tokens).
    java = _candidate("I like Java")
    decisions = _consolidate("I like Python", java)
    assert all(
        d.decision_type not in (ConsolidationDecisionType.SUPERSEDES,
                                ConsolidationDecisionType.CONTRADICTS)
        for d in decisions
    )
