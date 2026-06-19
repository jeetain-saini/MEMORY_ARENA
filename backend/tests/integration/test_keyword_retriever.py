"""Integration tests for KeywordRetriever (BM25 over SQLite)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.dto.retrieval_dto import MemorySearchQuery
from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.keyword_retriever import KeywordRetriever
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from tests.integration._db import make_engine, seed_user
from tests.integration._retrieval import make_uow_factory

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _save(uow_factory, memory: Memory) -> None:
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()


def test_keyword_matches_content() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow_factory = make_uow_factory(engine)

        paris = Memory.create(user_id=user_id, content="paris is the capital of france", memory_type=MemoryType.FACT)
        report = Memory.create(user_id=user_id, content="finish the quarterly report", memory_type=MemoryType.GOAL)
        await _save(uow_factory, paris)
        await _save(uow_factory, report)

        retriever = KeywordRetriever(uow_factory, RetrievalConfig())
        results = await retriever.retrieve(
            MemorySearchQuery(query="paris", user_id=user_id), limit=10
        )
        assert len(results) == 1
        assert results[0].memory.id == paris.id
        assert results[0].score > 0.0
        await engine.dispose()

    _run(scenario)


def test_keyword_searches_metadata() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow_factory = make_uow_factory(engine)

        m = Memory.create(
            user_id=user_id, content="a note", memory_type=MemoryType.FACT,
            metadata={"topic": "kubernetes"},
        )
        await _save(uow_factory, m)

        retriever = KeywordRetriever(uow_factory, RetrievalConfig())
        results = await retriever.retrieve(
            MemorySearchQuery(query="kubernetes", user_id=user_id), limit=10
        )
        assert len(results) == 1 and results[0].memory.id == m.id
        await engine.dispose()

    _run(scenario)


def test_keyword_no_match_returns_empty() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id = await seed_user(engine)
        uow_factory = make_uow_factory(engine)
        await _save(uow_factory, Memory.create(user_id=user_id, content="alpha beta", memory_type=MemoryType.FACT))

        retriever = KeywordRetriever(uow_factory, RetrievalConfig())
        results = await retriever.retrieve(
            MemorySearchQuery(query="gamma", user_id=user_id), limit=10
        )
        assert results == []
        await engine.dispose()

    _run(scenario)
