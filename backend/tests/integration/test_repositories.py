"""Repository + Unit-of-Work integration tests against an isolated DB.

Uses an in-memory SQLite database (``aiosqlite`` + ``StaticPool`` so the schema
persists across sessions). Async coroutines are driven with ``asyncio.run`` so
the suite needs no pytest-asyncio plugin. The cross-dialect Vector type lets the
full schema — including ``memory_embeddings`` — be created here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.application.dto.memory_dto import MemorySearchRequest
from app.domain.entities.memory import Memory
from app.domain.entities.memory_relation import MemoryRelation
from app.domain.entities.memory_score import MemoryScore
from app.domain.entities.memory_version import MemoryVersion
from app.domain.value_objects.memory_type import MemoryType
from app.domain.value_objects.relation_type import RelationType
from app.infrastructure.database.base import Base
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork

T = TypeVar("T")


async def _make_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def _seed_user(engine: AsyncEngine) -> uuid4:  # type: ignore[valid-type]
    user_id = uuid4()
    factory = create_session_factory(engine)
    async with factory() as session:
        session.add(UserModel(id=user_id, email=f"{user_id}@example.com"))
        await session.commit()
    return user_id


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def test_save_and_get_memory() -> None:
    async def scenario() -> None:
        engine = await _make_engine()
        user_id = await _seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))

        memory = Memory.create(
            user_id=user_id, content="User likes concise answers.", memory_type=MemoryType.PREFERENCE
        )
        async with uow:
            await uow.memories.save(memory)
            await uow.commit()

        async with uow:
            fetched = await uow.memories.get_by_id(memory.id)
        assert fetched is not None
        assert fetched.content == "User likes concise answers."
        assert fetched.memory_type is MemoryType.PREFERENCE
        await engine.dispose()

    _run(scenario)


def test_update_persists_content_and_score() -> None:
    async def scenario() -> None:
        engine = await _make_engine()
        user_id = await _seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))

        memory = Memory.create(user_id=user_id, content="v1", memory_type=MemoryType.FACT)
        async with uow:
            await uow.memories.save(memory)
            await uow.commit()

        memory.update_content("v2 content")
        memory.reinforce(step=0.2)
        async with uow:
            await uow.memories.update(memory)
            await uow.commit()

        async with uow:
            fetched = await uow.memories.get_by_id(memory.id)
        assert fetched is not None
        assert fetched.content == "v2 content"
        assert fetched.version == 2
        assert fetched.score.frequency == 0.2
        await engine.dispose()

    _run(scenario)


def test_soft_delete_hides_memory() -> None:
    async def scenario() -> None:
        engine = await _make_engine()
        user_id = await _seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))

        memory = Memory.create(user_id=user_id, content="to delete", memory_type=MemoryType.FACT)
        async with uow:
            await uow.memories.save(memory)
            await uow.commit()
        async with uow:
            await uow.memories.delete(memory.id)
            await uow.commit()

        async with uow:
            assert await uow.memories.get_by_id(memory.id) is None
            assert await uow.memories.list_by_user(user_id) == []
        await engine.dispose()

    _run(scenario)


def test_search_filters() -> None:
    async def scenario() -> None:
        engine = await _make_engine()
        user_id = await _seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))

        fact = Memory.create(user_id=user_id, content="Capital of France is Paris", memory_type=MemoryType.FACT)
        goal = Memory.create(
            user_id=user_id,
            content="Finish the report",
            memory_type=MemoryType.GOAL,
            score=MemoryScore(importance=1, utility=1, frequency=1, recency=1, confidence=1),
        )
        async with uow:
            await uow.memories.save(fact)
            await uow.memories.save(goal)
            await uow.commit()

        async with uow:
            by_type = await uow.memories.search(
                MemorySearchRequest(user_id=user_id, memory_types=[MemoryType.GOAL])
            )
            by_text = await uow.memories.search(
                MemorySearchRequest(user_id=user_id, query="paris")
            )
            high_score = await uow.memories.search(
                MemorySearchRequest(user_id=user_id, min_total_score=0.9)
            )
        assert {m.id for m in by_type} == {goal.id}
        assert {m.id for m in by_text} == {fact.id}
        assert {m.id for m in high_score} == {goal.id}
        await engine.dispose()

    _run(scenario)


def test_relations_and_versions() -> None:
    async def scenario() -> None:
        engine = await _make_engine()
        user_id = await _seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))

        a = Memory.create(user_id=user_id, content="A", memory_type=MemoryType.FACT)
        b = Memory.create(user_id=user_id, content="B", memory_type=MemoryType.FACT)
        relation = MemoryRelation.create(
            source_memory_id=a.id, target_memory_id=b.id, relation_type=RelationType.DEPENDS_ON
        )
        version = MemoryVersion.capture(a, reason="snapshot")

        async with uow:
            await uow.memories.save(a)
            await uow.memories.save(b)
            await uow.relations.save(relation)
            await uow.versions.save(version)
            await uow.commit()

        async with uow:
            rels = await uow.relations.list_for_memory(a.id)
            versions = await uow.versions.list_for_memory(a.id)
        assert len(rels) == 1 and rels[0].relation_type is RelationType.DEPENDS_ON
        assert len(versions) == 1 and versions[0].version_number == 1
        await engine.dispose()

    _run(scenario)


def test_rollback_discards_changes() -> None:
    async def scenario() -> None:
        engine = await _make_engine()
        user_id = await _seed_user(engine)
        uow = SQLAlchemyUnitOfWork(create_session_factory(engine))

        memory = Memory.create(user_id=user_id, content="never committed", memory_type=MemoryType.FACT)
        async with uow:
            await uow.memories.save(memory)
            await uow.rollback()

        async with uow:
            assert await uow.memories.get_by_id(memory.id) is None
        await engine.dispose()

    _run(scenario)
