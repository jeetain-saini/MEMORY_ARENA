"""Idempotent demo seeding for the free-tier portfolio deployment.

Creates two demo users and a small, illustrative memory set per user — including
a contradiction pair (to showcase conflict detection / CONTRADICTS edges) and
PROJECT/GOAL/EXPERIENCE memories (so rolling summaries have content). Memories
are created through ``CreateMemoryUseCase``, so the normal event pipeline runs:
embeddings are generated, the graph is synced, and consolidation derives edges —
exactly as a real write would. Re-running is safe: a user that already exists is
skipped entirely.

The demo user ids are fixed so the frontend's ``NEXT_PUBLIC_DEFAULT_USER_ID`` is
stable across deploys.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from app.application.dto.memory_dto import CreateMemoryRequest
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.summary_generator import SummaryGenerator
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.application.use_cases.memory_use_cases_impl import CreateMemoryUseCaseImpl
from app.domain.entities.user import User
from app.domain.value_objects.memory_type import MemoryType

ALICE = UUID("000000a1-0000-0000-0000-000000000001")
BOB = UUID("000000b0-0000-0000-0000-000000000002")

# (content, type) per demo user.
_DEMO: dict[UUID, tuple[str, str, list[tuple[str, MemoryType]]]] = {
    ALICE: (
        "alice@demo.memoryarena.app",
        "Demo Alice",
        [
            ("Alice uses Python and FastAPI for backend services", MemoryType.FACT),
            ("Experienced with async SQLAlchemy and pgvector", MemoryType.SKILL),
            ("Building MemoryArena, a self-evolving AI memory platform", MemoryType.PROJECT),
            ("Ship the analytics dashboard by Q3", MemoryType.GOAL),
            ("Prefers async standups over synchronous meetings", MemoryType.PREFERENCE),
            ("Gave a talk on Clean Architecture at the team summit", MemoryType.EXPERIENCE),
            ("I use Postgres for the primary datastore", MemoryType.FACT),
            ("I no longer use Postgres; the demo runs on SQLite", MemoryType.FACT),
        ],
    ),
    BOB: (
        "bob@demo.memoryarena.app",
        "Demo Bob",
        [
            ("Bob is learning Rust this quarter", MemoryType.GOAL),
            ("Prefers detailed written specs before coding", MemoryType.PREFERENCE),
            ("Migrating the billing service to event-driven workflows", MemoryType.PROJECT),
            ("Attended the distributed-systems design workshop", MemoryType.EXPERIENCE),
            ("Knows Go, Kafka, and Kubernetes", MemoryType.SKILL),
        ],
    ),
}


async def seed_demo(
    uow_factory: Callable[[], UnitOfWork],
    dispatcher: EventDispatcher,
    *,
    summary_generator: SummaryGenerator | None = None,
) -> dict[str, int]:
    """Idempotently seed demo users + memories (+ summaries). Returns counts."""
    created_users = 0
    created_memories = 0

    for user_id, (email, display_name, memories) in _DEMO.items():
        async with uow_factory() as uow:
            if await uow.users.get_by_id(user_id) is not None:
                continue  # already seeded — skip this user entirely (idempotent)

        async with uow_factory() as uow:
            await uow.users.add(User(id=user_id, email=email, display_name=display_name))
            await uow.commit()
        created_users += 1

        for content, memory_type in memories:
            use_case = CreateMemoryUseCaseImpl(uow_factory(), dispatcher)
            await use_case.execute(
                CreateMemoryRequest(user_id=user_id, content=content, memory_type=memory_type)
            )
            created_memories += 1

        if summary_generator is not None:
            await MemorySummaryService(uow_factory, summary_generator).refresh(user_id)

    return {"users": created_users, "memories": created_memories}
