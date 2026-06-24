"""Regression: creating a memory for a not-yet-registered user auto-provisions
the user, so the memories.user_id -> users.id FK is satisfied.

This is the bug that made Agent Playground / conversation-capture memories never
persist: the frontend picks an arbitrary user_id (no auth), so the background
ingest job failed with a ForeignKeyViolationError and the memory silently
vanished. The write path must create the user on first write.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.memory_dto import CreateMemoryRequest
from app.application.use_cases.ingest_memory_use_cases_impl import IngestMemoryUseCaseImpl
from app.application.use_cases.memory_use_cases_impl import CreateMemoryUseCaseImpl
from app.application.interfaces.workflow_job_processor import WorkflowJob
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.llm.graphs.factory import build_workflow_engine
from tests.integration._db import make_engine


def test_create_memory_autoprovisions_unknown_user() -> None:
    async def scenario() -> None:
        engine = await make_engine()  # fresh DB, NO users seeded
        sf = create_session_factory(engine)
        uow_factory = lambda: SQLAlchemyUnitOfWork(sf)
        user = uuid4()  # never registered

        # Before: the user does not exist.
        async with uow_factory() as uow:
            assert await uow.users.get_by_id(user) is None

        create = CreateMemoryUseCaseImpl(uow_factory(), InProcessEventDispatcher())
        resp = await create.execute(CreateMemoryRequest(
            user_id=user, content="My favorite programming language is Rust",
            memory_type=MemoryType.PREFERENCE, metadata={}))

        async with uow_factory() as uow:
            assert await uow.users.get_by_id(user) is not None      # user provisioned
            mems = await uow.memories.list_for_analytics(user)
        assert len(mems) == 1 and mems[0].id == resp.id              # memory persisted
        await engine.dispose()

    asyncio.run(scenario())


def test_ingest_pipeline_persists_for_unknown_user() -> None:
    """The exact failing path: conversation capture / ingest for a new user."""

    async def scenario() -> None:
        engine = await make_engine()
        sf = create_session_factory(engine)
        uow_factory = lambda: SQLAlchemyUnitOfWork(sf)
        user = uuid4()

        ingest = IngestMemoryUseCaseImpl(build_workflow_engine(), uow_factory,
                                         InProcessEventDispatcher())
        await ingest.process(WorkflowJob(
            job_id=uuid4(), user_id=user,
            raw_text="My favorite programming language is Rust.",
            metadata={"source": "conversation"}))

        async with uow_factory() as uow:
            mems = await uow.memories.list_for_analytics(user)
        assert len(mems) >= 1  # would be 0 before the fix (FK violation)
        await engine.dispose()

    asyncio.run(scenario())
