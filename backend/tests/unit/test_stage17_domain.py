"""Stage 17 unit tests: lifecycle transitions, category mapping, retrieval
tracking, and importance evolution (pure domain / service logic — no DB)."""

from __future__ import annotations

import pytest

from app.application.services.intelligence.importance_evolution import (
    ImportanceEvolutionService,
)
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.exceptions.errors import InvalidMemoryStateError
from app.domain.value_objects.memory_category import MemoryCategory, default_category
from app.domain.value_objects.memory_status import RETRIEVABLE_STATUSES, MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from uuid import uuid4


def _mem(content="I am learning LangGraph", mtype=MemoryType.EXPERIENCE, score=None) -> Memory:
    return Memory.create(user_id=uuid4(), content=content, memory_type=mtype, score=score)


# --- lifecycle transitions -------------------------------------------------

def test_only_active_is_retrievable() -> None:
    assert RETRIEVABLE_STATUSES == frozenset({MemoryStatus.ACTIVE})
    for hidden in (MemoryStatus.ARCHIVED, MemoryStatus.SUPERSEDED, MemoryStatus.FORGOTTEN,
                   MemoryStatus.DELETED):
        assert hidden not in RETRIEVABLE_STATUSES


def test_supersede_transition_and_event() -> None:
    m = _mem()
    other = uuid4()
    m.supersede(superseded_by_id=other)
    assert m.status is MemoryStatus.SUPERSEDED
    assert any(type(e).__name__ == "MemorySuperseded" for e in m.pull_events())


def test_forget_transition_and_event() -> None:
    m = _mem()
    m.forget(reason="aged out")
    assert m.status is MemoryStatus.FORGOTTEN
    assert any(type(e).__name__ == "MemoryForgotten" for e in m.pull_events())


def test_restore_from_superseded_and_forgotten() -> None:
    m = _mem()
    m.supersede(superseded_by_id=uuid4())
    m.restore()
    assert m.status is MemoryStatus.ACTIVE
    m.forget()
    m.restore()
    assert m.status is MemoryStatus.ACTIVE


def test_forgotten_cannot_be_superseded() -> None:
    m = _mem()
    m.forget()
    with pytest.raises(InvalidMemoryStateError):
        m.supersede(superseded_by_id=uuid4())


def test_deleted_is_terminal() -> None:
    m = _mem()
    m.delete()
    for op in (lambda: m.forget(), lambda: m.supersede(superseded_by_id=uuid4()), m.restore):
        with pytest.raises(InvalidMemoryStateError):
            op()


# --- category --------------------------------------------------------------

def test_default_category_mapping() -> None:
    assert default_category(MemoryType.EXPERIENCE) is MemoryCategory.EPISODIC
    for t in (MemoryType.FACT, MemoryType.SKILL, MemoryType.GOAL, MemoryType.PROJECT,
              MemoryType.PREFERENCE):
        assert default_category(t) is MemoryCategory.SEMANTIC


def test_memory_derives_and_overrides_category() -> None:
    episodic = _mem(mtype=MemoryType.EXPERIENCE)
    assert episodic.category is MemoryCategory.EPISODIC
    episodic.reclassify(MemoryCategory.SEMANTIC)
    assert episodic.category is MemoryCategory.SEMANTIC
    assert _mem(content="tz is IST", mtype=MemoryType.FACT).category is MemoryCategory.SEMANTIC


# --- retrieval tracking ----------------------------------------------------

def test_record_retrieval_increments_without_event() -> None:
    m = _mem()
    m.pull_events()  # clear creation event
    assert m.retrieval_count == 0 and m.last_retrieved_at is None
    m.record_retrieval()
    m.record_retrieval()
    assert m.retrieval_count == 2
    assert m.last_retrieved_at is not None
    assert m.pull_events() == []  # no domain event from a read-side signal


# --- importance evolution --------------------------------------------------

def test_importance_grows_with_frequency_and_signals() -> None:
    svc = ImportanceEvolutionService()
    base = _mem(score=MemoryScore(importance=0.3, utility=0.3, frequency=0.3,
                                  recency=0.3, confidence=0.5))
    cold = svc.next_importance(base)
    base.retrieval_count = 10  # saturates frequency signal
    hot = svc.next_importance(base, centrality=1.0, contradiction_involved=True)
    assert 0.0 <= cold <= 1.0 and 0.0 <= hot <= 1.0
    assert hot > cold


def test_importance_is_deterministic_and_clamped() -> None:
    svc = ImportanceEvolutionService()
    m = _mem(score=MemoryScore(importance=1.0, utility=1.0, frequency=1.0,
                               recency=1.0, confidence=1.0))
    m.retrieval_count = 999
    a = svc.next_importance(m, centrality=1.0, contradiction_involved=True)
    b = svc.next_importance(m, centrality=1.0, contradiction_involved=True)
    assert a == b
    assert a <= 1.0
