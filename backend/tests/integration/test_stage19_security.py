"""Stage 19.2 / 19.5 — tenant-isolation & security verification.

Exercises the RBAC dimension end-to-end through the real MemoryService:

  * tenant escape — a USER/SERVICE principal cannot reach another tenant's
    memory (404, existence not leaked);
  * admin reach — an ADMIN principal may read across tenants (cross-tenant);
  * privilege escalation — require_role denies a USER an admin-only operation.

Complements test_authorization_service_level (role-agnostic ownership) and
test_stage19_rbac (pure policy). SQLite + in-memory dispatcher.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import uuid4

import pytest

from app.application.dto.auth_dto import AuthPrincipal
from app.application.exceptions import AuthorizationError, ResourceNotFoundForCaller
from app.application.services.authorization import require_role
from app.application.services.memory_service import MemoryService
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.domain.value_objects.role import Role
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
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
    return engine, factory, other_memory


def _svc(factory, user_id, role: Role) -> MemoryService:
    return MemoryService(
        SQLAlchemyUnitOfWork(factory),
        InProcessEventDispatcher(),
        AuthPrincipal(user_id=user_id, tenant_id=user_id, role=role),
    )


# --- tenant escape (19.2) --------------------------------------------------

def test_user_cannot_read_other_tenant_memory() -> None:
    async def scenario() -> None:
        engine, factory, other_memory = await _setup()
        svc = _svc(factory, OWNER, Role.USER)
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.get_by_id(other_memory.id)
        await engine.dispose()

    _run(scenario)


def test_service_role_cannot_read_other_tenant_memory() -> None:
    async def scenario() -> None:
        engine, factory, other_memory = await _setup()
        svc = _svc(factory, OWNER, Role.SERVICE)
        with pytest.raises(ResourceNotFoundForCaller):
            await svc.get_by_id(other_memory.id)
        await engine.dispose()

    _run(scenario)


# --- admin reach (19.2) ----------------------------------------------------

def test_admin_can_read_across_tenants() -> None:
    async def scenario() -> None:
        engine, factory, other_memory = await _setup()
        admin = _svc(factory, OWNER, Role.ADMIN)
        result = await admin.get_by_id(other_memory.id)
        assert result.id == other_memory.id   # cross-tenant read permitted
        await engine.dispose()

    _run(scenario)


# --- privilege escalation (19.5) -------------------------------------------

def test_user_denied_admin_only_operation() -> None:
    # A USER principal cannot pass an admin-only role gate; ADMIN can.
    user = AuthPrincipal(user_id=OWNER, tenant_id=OWNER, role=Role.USER)
    admin = AuthPrincipal(user_id=OWNER, tenant_id=OWNER, role=Role.ADMIN)
    with pytest.raises(AuthorizationError):
        require_role(user, Role.ADMIN)
    require_role(admin, Role.ADMIN)  # allowed


def test_service_denied_admin_only_operation() -> None:
    service = AuthPrincipal(user_id=OWNER, tenant_id=OWNER, role=Role.SERVICE)
    with pytest.raises(AuthorizationError):
        require_role(service, Role.ADMIN)
