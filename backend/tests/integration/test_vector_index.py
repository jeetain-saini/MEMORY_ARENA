"""VectorIndex tests (Stage 14 Phase 5): parity + filters + factory.

Confirms BruteForceVectorIndex, the repository's search_similar fallback, and the
legacy VectorRetriever path all produce identical rankings under SQLite (the
offline-deterministic guarantee), and that filters/limit are honored.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "secret")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

from app.application.dto.retrieval_dto import MemorySearchQuery
from app.application.services.retrieval.brute_force_index import BruteForceVectorIndex
from app.application.services.retrieval.vector_retriever import VectorRetriever
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from tests.integration._db import make_engine, seed_user
from tests.integration._retrieval import make_provider, make_uow_factory, save_and_embed

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _seed(uow_factory, provider, user):
    m1 = Memory.create(user_id=user, content="alpha beta gamma", memory_type=MemoryType.FACT)
    m2 = Memory.create(user_id=user, content="delta epsilon zeta", memory_type=MemoryType.GOAL)
    m3 = Memory.create(user_id=user, content="alpha beta delta", memory_type=MemoryType.FACT)
    for m in (m1, m2, m3):
        await save_and_embed(uow_factory, provider, m)
    return m1, m2, m3


def test_brute_force_index_parity_with_repo_and_retriever() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        provider = make_provider()
        await _seed(uow_factory, provider, user)
        qv = await provider.embed_text("alpha beta gamma")
        mname = provider.model_name

        index = BruteForceVectorIndex(uow_factory)
        idx = await index.search(user, qv, limit=10, model_name=mname)

        async with uow_factory() as uow:
            repo = await uow.embeddings.search_similar(user, qv, limit=10, model_name=mname)

        # Index and the repository's SQLite fallback agree exactly.
        assert [(m.id, round(s, 6)) for m, s in idx] == [(m.id, round(s, 6)) for m, s in repo]

        # Legacy VectorRetriever (index defaults to brute-force) gives same order.
        retriever = VectorRetriever(uow_factory, provider)
        legacy = await retriever.retrieve(MemorySearchQuery(query="alpha beta gamma", user_id=user), limit=10)
        assert [sm.memory.id for sm in legacy] == [m.id for m, _ in idx]
        await engine.dispose()

    _run(scenario)


def test_index_respects_type_filter() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        provider = make_provider()
        _m1, m2_goal, _m3 = await _seed(uow_factory, provider, user)
        qv = await provider.embed_text("alpha beta gamma")

        index = BruteForceVectorIndex(uow_factory)
        results = await index.search(
            user, qv, limit=10, model_name=provider.model_name, memory_types=[MemoryType.FACT]
        )
        ids = {m.id for m, _ in results}
        assert m2_goal.id not in ids  # GOAL filtered out
        assert len(ids) == 2
        await engine.dispose()

    _run(scenario)


def test_index_honors_limit_ordered_by_score() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        provider = make_provider()
        m1, _m2, _m3 = await _seed(uow_factory, provider, user)
        qv = await provider.embed_text("alpha beta gamma")

        results = await BruteForceVectorIndex(uow_factory).search(
            user, qv, limit=1, model_name=provider.model_name
        )
        assert len(results) == 1
        assert results[0][0].id == m1.id  # exact-match content ranks first
        await engine.dispose()

    _run(scenario)


def test_factory_selection() -> None:
    from app.core.config import get_settings
    from app.infrastructure.vector.factory import build_vector_index
    from app.infrastructure.vector.pgvector_index import PgVectorIndex

    def _uow():  # pragma: no cover - not invoked by the factory
        raise NotImplementedError

    get_settings.cache_clear()
    try:
        assert isinstance(build_vector_index(_uow), BruteForceVectorIndex)  # scan default
        os.environ["VECTOR_SEARCH_MODE"] = "hnsw"
        get_settings.cache_clear()
        assert isinstance(build_vector_index(_uow), PgVectorIndex)
    finally:
        os.environ.pop("VECTOR_SEARCH_MODE", None)
        get_settings.cache_clear()
