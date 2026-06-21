"""Integration tests for idempotent demo seeding (deployment-readiness)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.seed.demo_seed import ALICE, BOB, seed_demo
from app.infrastructure.summaries.deterministic_summary_generator import (
    DeterministicSummaryGenerator,
)
from tests.integration._db import make_engine

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def test_seed_is_idempotent_and_populates() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        factory = create_session_factory(engine)

        def uow_factory() -> SQLAlchemyUnitOfWork:
            return SQLAlchemyUnitOfWork(factory)

        dispatcher = InProcessEventDispatcher()  # fresh; no side-effect handlers
        gen = DeterministicSummaryGenerator()

        first = await seed_demo(uow_factory, dispatcher, summary_generator=gen)
        assert first == {"users": 2, "memories": 13}  # 8 alice + 5 bob

        # Re-running seeds nothing new (idempotent).
        second = await seed_demo(uow_factory, dispatcher, summary_generator=gen)
        assert second == {"users": 0, "memories": 0}

        async with uow_factory() as uow:
            alice_memories = await uow.memories.list_by_user(ALICE, limit=100)
            bob_memories = await uow.memories.list_by_user(BOB, limit=100)
            alice_summaries = await uow.summaries.list_for_user(ALICE)
            alice_user = await uow.users.get_by_id(ALICE)

        assert len(alice_memories) == 8
        assert len(bob_memories) == 5
        assert len(alice_summaries) >= 1            # PROJECT/GOAL/EXPERIENCE summaries
        assert alice_user is not None
        assert alice_user.tenant_id == ALICE        # each demo user is its own tenant

    _run(scenario)
