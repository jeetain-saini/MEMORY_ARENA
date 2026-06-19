"""Memory API endpoints (API v1).

Thin HTTP adapters: validate input via pydantic schemas, delegate to the
``MemoryService``, and wrap results in the standardized ``APIResponse``
envelope. No business logic lives here — domain rules and orchestration are in
the application layer; error→HTTP mapping is centralized in core exception
handlers.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies.providers import MemoryServiceDep
from app.application.services.memory_service import MemoryService
from app.core.logging import get_request_id
from app.schemas.memory import (
    CreateMemoryRequestSchema,
    MemoryResponseSchema,
    MemorySearchRequestSchema,
    UpdateMemoryRequestSchema,
)
from app.schemas.responses import APIResponse

router = APIRouter(prefix="/memories", tags=["memories"])


def _ok(data: Any) -> APIResponse[Any]:
    return APIResponse(data=data, request_id=get_request_id())


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponse[MemoryResponseSchema],
    summary="Create a memory",
)
async def create_memory(
    payload: CreateMemoryRequestSchema,
    service: MemoryService = MemoryServiceDep,
) -> APIResponse[MemoryResponseSchema]:
    result = await service.create(payload.to_dto())
    return _ok(MemoryResponseSchema.from_dto(result))


@router.post(
    "/search",
    response_model=APIResponse[list[MemoryResponseSchema]],
    summary="Search a user's memories",
)
async def search_memories(
    payload: MemorySearchRequestSchema,
    service: MemoryService = MemoryServiceDep,
) -> APIResponse[list[MemoryResponseSchema]]:
    results = await service.search(payload.to_dto())
    return _ok([MemoryResponseSchema.from_dto(r) for r in results])


@router.get(
    "/user/{user_id}",
    response_model=APIResponse[list[MemoryResponseSchema]],
    summary="List a user's memories",
)
async def list_user_memories(
    user_id: UUID,
    service: MemoryService = MemoryServiceDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> APIResponse[list[MemoryResponseSchema]]:
    results = await service.list_by_user(user_id, limit=limit, offset=offset)
    return _ok([MemoryResponseSchema.from_dto(r) for r in results])


@router.get(
    "/{memory_id}",
    response_model=APIResponse[MemoryResponseSchema],
    summary="Get a memory by id",
)
async def get_memory(
    memory_id: UUID,
    service: MemoryService = MemoryServiceDep,
) -> APIResponse[MemoryResponseSchema]:
    result = await service.get_by_id(memory_id)
    return _ok(MemoryResponseSchema.from_dto(result))


@router.put(
    "/{memory_id}",
    response_model=APIResponse[MemoryResponseSchema],
    summary="Update a memory",
)
async def update_memory(
    memory_id: UUID,
    payload: UpdateMemoryRequestSchema,
    service: MemoryService = MemoryServiceDep,
) -> APIResponse[MemoryResponseSchema]:
    result = await service.update(payload.to_dto(memory_id))
    return _ok(MemoryResponseSchema.from_dto(result))


@router.delete(
    "/{memory_id}",
    response_model=APIResponse[dict[str, Any]],
    summary="Delete (soft) a memory",
)
async def delete_memory(
    memory_id: UUID,
    service: MemoryService = MemoryServiceDep,
    user_id: UUID = Query(..., description="Owner of the memory"),
) -> APIResponse[dict[str, Any]]:
    await service.delete(memory_id=memory_id, user_id=user_id)
    return _ok({"memory_id": str(memory_id), "deleted": True})
