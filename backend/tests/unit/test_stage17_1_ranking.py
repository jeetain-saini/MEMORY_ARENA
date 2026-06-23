"""Stage 17.1 ranking proofs: retrieval_count, importance, promotion/semantic,
and cluster membership each move the memory-boost ranking signal."""

from __future__ import annotations

from uuid import uuid4

from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.scoring import memory_boost_score
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_type import MemoryType

CFG = RetrievalConfig()


def _memory(
    *,
    score: MemoryScore,
    retrieval_count: int = 0,
    promoted: bool = False,
    category: MemoryCategory = MemoryCategory.SEMANTIC,
    cluster_id: str | None = None,
) -> Memory:
    meta = {"cluster_id": cluster_id} if cluster_id else {}
    m = Memory(
        user_id=uuid4(),
        content="x",
        memory_type=MemoryType.FACT,
        score=score,
        metadata=meta,
        category=category,
        retrieval_count=retrieval_count,
    )
    m.is_promoted = promoted
    return m


# C) retrieval_count changes ranking ----------------------------------------
def test_retrieval_count_increases_rank() -> None:
    s = MemoryScore(importance=0.3, utility=0.3, frequency=0.3, recency=0.3, confidence=0.3)
    cold = _memory(score=s, retrieval_count=0)
    hot = _memory(score=s, retrieval_count=CFG.retrieval_saturation)
    assert memory_boost_score(hot, CFG) > memory_boost_score(cold, CFG)


# D) importance changes ranking ---------------------------------------------
def test_importance_increases_rank() -> None:
    low = _memory(score=MemoryScore(importance=0.2, utility=0.0, frequency=0.0))
    high = _memory(score=MemoryScore(importance=0.9, utility=0.0, frequency=0.0))
    assert memory_boost_score(high, CFG) > memory_boost_score(low, CFG)


# E) promoted + semantic memories rank higher -------------------------------
def test_promoted_memory_ranks_higher() -> None:
    s = MemoryScore(importance=0.4, utility=0.4, frequency=0.4)
    plain = _memory(score=s, promoted=False)
    promoted = _memory(score=s, promoted=True)
    assert memory_boost_score(promoted, CFG) > memory_boost_score(plain, CFG)


def test_semantic_memory_ranks_higher_than_episodic() -> None:
    s = MemoryScore(importance=0.4, utility=0.4, frequency=0.4)
    episodic = _memory(score=s, category=MemoryCategory.EPISODIC)
    semantic = _memory(score=s, category=MemoryCategory.SEMANTIC)
    assert memory_boost_score(semantic, CFG) > memory_boost_score(episodic, CFG)


# F) cluster membership changes ranking -------------------------------------
def test_cluster_membership_increases_rank() -> None:
    s = MemoryScore(importance=0.4, utility=0.4, frequency=0.4)
    unclustered = _memory(score=s, cluster_id=None)
    clustered = _memory(score=s, cluster_id="abc123")
    assert memory_boost_score(clustered, CFG) > memory_boost_score(unclustered, CFG)


def test_boost_stays_in_unit_range() -> None:
    maxed = _memory(
        score=MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1),
        retrieval_count=99,
        promoted=True,
        cluster_id="c",
    )
    assert 0.0 <= memory_boost_score(maxed, CFG) <= 1.0
