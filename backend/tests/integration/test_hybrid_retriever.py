"""Integration tests for HybridRetriever fusion."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.dto.retrieval_dto import MemorySearchQuery
from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.hybrid_retriever import HybridRetriever
from app.application.services.retrieval.keyword_retriever import KeywordRetriever
from app.application.services.retrieval.vector_retriever import VectorRetriever
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from tests.integration._db import make_engine, seed_user
from tests.integration._retrieval import make_provider, make_uow_factory, save_and_embed

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _build(engine):
    user_id = await seed_user(engine)
    uow_factory = make_uow_factory(engine)
    provider = make_provider()
    config = RetrievalConfig()
    hybrid = HybridRetriever(
        VectorRetriever(uow_factory, provider),
        KeywordRetriever(uow_factory, config),
        config,
    )
    return user_id, uow_factory, provider, hybrid


def test_fusion_ranks_relevant_memory_first() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, hybrid = await _build(engine)

        relevant = Memory.create(user_id=user_id, content="machine learning embeddings tutorial", memory_type=MemoryType.FACT)
        noise1 = Memory.create(user_id=user_id, content="dentist appointment on tuesday", memory_type=MemoryType.FACT)
        noise2 = Memory.create(user_id=user_id, content="buy milk and eggs", memory_type=MemoryType.FACT)
        for m in (relevant, noise1, noise2):
            await save_and_embed(uow_factory, provider, m)

        query = MemorySearchQuery(query="machine learning embeddings tutorial", user_id=user_id)
        results = await hybrid.retrieve(query)

        assert results[0].memory_id == relevant.id
        # Every fused candidate carries a full breakdown in [0, 1].
        for r in results:
            for value in (r.scores.vector_score, r.scores.bm25_score,
                          r.scores.memory_score, r.scores.recency_score):
                assert 0.0 <= value <= 1.0
        await engine.dispose()

    _run(scenario)


def test_fusion_unions_vector_and_keyword_candidates() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, hybrid = await _build(engine)
        for i in range(3):
            await save_and_embed(
                uow_factory, provider,
                Memory.create(user_id=user_id, content=f"topic {i} alpha", memory_type=MemoryType.FACT),
            )

        results = await hybrid.retrieve(MemorySearchQuery(query="alpha", user_id=user_id))
        # All three are embedded, so vector retrieval surfaces them all.
        assert len(results) == 3
        await engine.dispose()

    _run(scenario)


def test_fusion_weights_change_ranking() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        provider = make_provider()

        # m_lexical matches the query lexically; m_other does not.
        m_lexical = Memory.create(user_id=user_id, content="alpha alpha alpha", memory_type=MemoryType.FACT)
        m_other = Memory.create(user_id=user_id, content="zeta omega", memory_type=MemoryType.FACT)
        await save_and_embed(uow_factory, provider, m_lexical)
        await save_and_embed(uow_factory, provider, m_other)

        bm25_heavy = RetrievalConfig(weight_vector=0.0, weight_bm25=1.0, weight_memory=0.0, weight_recency=0.0)
        hybrid = HybridRetriever(
            VectorRetriever(uow_factory, provider),
            KeywordRetriever(uow_factory, bm25_heavy),
            bm25_heavy,
        )
        results = await hybrid.retrieve(MemorySearchQuery(query="alpha", user_id=user_id))
        assert results[0].memory_id == m_lexical.id
        await engine.dispose()

    _run(scenario)
