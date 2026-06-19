"""Integration tests for VectorRetriever (SQLite + deterministic embeddings)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.dto.retrieval_dto import MemorySearchQuery
from app.application.services.retrieval.vector_retriever import VectorRetriever
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from tests.integration._db import make_engine, seed_user
from tests.integration._retrieval import make_provider, make_uow_factory, save_and_embed

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def test_vector_ranks_semantically_closest_first() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        provider = make_provider()

        target = Memory.create(user_id=user_id, content="the capital of france is paris", memory_type=MemoryType.FACT)
        other = Memory.create(user_id=user_id, content="weekly grocery shopping list", memory_type=MemoryType.FACT)
        await save_and_embed(uow_factory, provider, target)
        await save_and_embed(uow_factory, provider, other)

        retriever = VectorRetriever(uow_factory, provider)
        query = MemorySearchQuery(query="the capital of france is paris", user_id=user_id)
        results = await retriever.retrieve(query, limit=10)

        assert results[0].memory.id == target.id
        assert results[0].score > 0.99  # identical text -> cosine ~1.0
        await engine.dispose()

    _run(scenario)


def test_vector_empty_query_returns_nothing() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        retriever = VectorRetriever(uow_factory, make_provider())
        results = await retriever.retrieve(MemorySearchQuery(query="   ", user_id=user_id), limit=10)
        assert results == []
        await engine.dispose()

    _run(scenario)


def test_vector_respects_limit() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        provider = make_provider()
        for i in range(5):
            m = Memory.create(user_id=user_id, content=f"memory number {i}", memory_type=MemoryType.FACT)
            await save_and_embed(uow_factory, provider, m)

        retriever = VectorRetriever(uow_factory, provider)
        results = await retriever.retrieve(MemorySearchQuery(query="memory", user_id=user_id), limit=3)
        assert len(results) == 3
        await engine.dispose()

    _run(scenario)
