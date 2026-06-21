"""Service-level authorization tests: cross-user by-id access -> 404.

Exercises the ownership guard in MemoryService, MemoryIntelligenceService, and
GraphTraversalService directly (single-loop SQLite + in-memory graph), where a
resource must be loaded to know its owner.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

import pytest

from app.application.dto.auth_dto import AuthPrincipal
from app.application.dto.graph_dto import GraphNode, NodeType
from app.application.dto.memory_dto import UpdateMemoryRequest
from app.application.exceptions import MemoryNotFoundException, ResourceNotFoundForCaller
from app.application.services.graph.traversal_service import GraphTraversalService
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.application.services.memory_service import MemoryService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")
OWNER = uuid4()
OTHER = uuid4()


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _seed_memory(factory, owner) -> Memory:
    memory = Memory.create(user_id=owner, content="secret", memory_type=MemoryType.FACT)
    async with SQLAlchemyUnitOfWork(factory) as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


async def _setup():
    engine = await make_engine()
    await seed_user(engine, OWNER)
    await seed_user(engine, OTHER)
    factory = create_session_factory(engine)
    other_memory = await _seed_memory(factory, OTHER)
    return factory, other_memory


def test_memory_get_by_id_other_user_is_not_found() -> None:
    async def scenario() -> None:
        factory, other_memory = await _setup()
        svc = MemoryService(
            SQLAlchemyUnitOfWork(factory),
            InProcessEventDispatcher(),
            AuthPrincipal(user_id=OWNER, tenant_id=OWNER),
        )
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.get_by_id(other_memory.id)

    _run(scenario)


def test_memory_update_other_user_is_not_found() -> None:
    async def scenario() -> None:
        factory, other_memory = await _setup()
        svc = MemoryService(
            SQLAlchemyUnitOfWork(factory),
            InProcessEventDispatcher(),
            AuthPrincipal(user_id=OWNER, tenant_id=OWNER),
        )
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.update(
                UpdateMemoryRequest(memory_id=other_memory.id, user_id=OWNER, content="hacked")
            )

    _run(scenario)


def test_memory_delete_other_user_is_not_found() -> None:
    async def scenario() -> None:
        factory, other_memory = await _setup()
        svc = MemoryService(
            SQLAlchemyUnitOfWork(factory),
            InProcessEventDispatcher(),
            AuthPrincipal(user_id=OWNER, tenant_id=OWNER),
        )
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.delete(memory_id=other_memory.id, user_id=OWNER)

    _run(scenario)


def test_owner_can_access_own_memory() -> None:
    async def scenario() -> None:
        factory, _other = await _setup()
        own = await _seed_memory(factory, OWNER)
        svc = MemoryService(
            SQLAlchemyUnitOfWork(factory),
            InProcessEventDispatcher(),
            AuthPrincipal(user_id=OWNER, tenant_id=OWNER),
        )
        result = await svc.get_by_id(own.id)
        assert result.id == own.id

    _run(scenario)


def test_intelligence_actions_on_other_user_are_not_found() -> None:
    # An authenticated OWNER targeting OTHER's memory is blocked by the ownership
    # guard (404) regardless of the user_id supplied: passing user_id=OTHER reaches
    # authorize_owner (-> ResourceNotFoundForCaller); passing user_id=OWNER is
    # blocked even earlier by the pre-existing user-scope check (MemoryNotFound).
    async def scenario() -> None:
        factory, other_memory = await _setup()
        svc = MemoryIntelligenceService(
            SQLAlchemyUnitOfWork(factory),
            InProcessEventDispatcher(),
            principal=AuthPrincipal(user_id=OWNER, tenant_id=OWNER),
        )
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.reinforce_memory(other_memory.id, user_id=OTHER)
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.promote_memory(other_memory.id, user_id=OTHER)
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.archive_memory(other_memory.id, user_id=OTHER)
        # And via the owner's own scope it is a plain not-found (still 404).
        with pytest.raises(MemoryNotFoundException):
            await svc.reinforce_memory(other_memory.id, user_id=OWNER)

    _run(scenario)


def test_no_principal_skips_ownership_check() -> None:
    # Backward compatibility: with auth disabled (principal None) the prior
    # behavior holds — a missing memory raises MemoryNotFound, not Authorization.
    async def scenario() -> None:
        factory, _other = await _setup()
        svc = MemoryService(SQLAlchemyUnitOfWork(factory), InProcessEventDispatcher())
        with pytest.raises(MemoryNotFoundException):
            await svc.get_by_id(uuid4())

    _run(scenario)


def test_graph_traverse_other_user_node_is_not_found() -> None:
    async def scenario() -> None:
        repo = InMemoryGraphRepository()
        node_id = str(uuid4())
        await repo.create_node(
            GraphNode(node_id=node_id, node_type=NodeType.MEMORY, label="x",
                      properties={"user_id": str(OTHER)})
        )
        svc = GraphTraversalService(repo, principal=AuthPrincipal(user_id=OWNER, tenant_id=OWNER))
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.traverse(node_id, depth=1)

    _run(scenario)
