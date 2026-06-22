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

from app.api.v1.dependencies.providers import (
    ContradictionResolutionServiceDep,
    MemoryAnalyticsServiceDep,
    MemoryHealthServiceDep,
    MemoryIntelligenceServiceDep,
    MemoryServiceDep,
)
from app.application.services.contradiction_resolution_service import (
    ContradictionResolutionService,
)
from app.application.services.memory_analytics_service import MemoryAnalyticsService
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.application.services.memory_service import MemoryService
from app.application.services.observability.memory_health_service import MemoryHealthService
from app.core.logging import get_request_id
from app.schemas.analytics import AnalyticsResponseSchema
from app.schemas.health import MemoryHealthResponseSchema
from app.schemas.memory import (
    ContradictionResolutionResponseSchema,
    CreateMemoryRequestSchema,
    MemoryResponseSchema,
    MemorySearchRequestSchema,
    ResolveContradictionRequestSchema,
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


@router.post(
    "/contradictions/resolve",
    response_model=APIResponse[ContradictionResolutionResponseSchema],
    summary="Resolve a contradiction: keep one memory, archive the obsolete one",
)
async def resolve_contradiction(
    payload: ResolveContradictionRequestSchema,
    service: ContradictionResolutionService = ContradictionResolutionServiceDep,
) -> APIResponse[ContradictionResolutionResponseSchema]:
    result = await service.resolve(
        keep_id=payload.keep_id, archive_id=payload.archive_id, user_id=payload.user_id
    )
    return _ok(ContradictionResolutionResponseSchema.from_dto(result))


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
    "/analytics",
    response_model=APIResponse[AnalyticsResponseSchema],
    summary="Aggregate memory analytics",
)
async def memory_analytics(
    service: MemoryAnalyticsService = MemoryAnalyticsServiceDep,
    user_id: UUID | None = Query(default=None, description="Optional: scope to one user"),
) -> APIResponse[AnalyticsResponseSchema]:
    result = await service.get_analytics(user_id)
    return _ok(AnalyticsResponseSchema.from_dto(result))


@router.get(
    "/health",
    response_model=APIResponse[MemoryHealthResponseSchema],
    summary="Memory health metrics (growth, rates, graph density, summary coverage)",
)
async def memory_health(
    service: MemoryHealthService = MemoryHealthServiceDep,
    user_id: UUID | None = Query(default=None, description="Optional: scope to one user"),
) -> APIResponse[MemoryHealthResponseSchema]:
    result = await service.get_health(user_id)
    return _ok(MemoryHealthResponseSchema.from_dto(result))


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


# --- Memory Intelligence actions ------------------------------------------
@router.post(
    "/{memory_id}/reinforce",
    response_model=APIResponse[MemoryResponseSchema],
    summary="Reinforce a memory (successful reuse)",
)
async def reinforce_memory(
    memory_id: UUID,
    service: MemoryIntelligenceService = MemoryIntelligenceServiceDep,
    user_id: UUID = Query(..., description="Owner of the memory"),
    step: float | None = Query(default=None, ge=0.0, le=1.0),
) -> APIResponse[MemoryResponseSchema]:
    result = await service.reinforce_memory(memory_id, user_id=user_id, step=step)
    return _ok(MemoryResponseSchema.from_dto(result))


@router.post(
    "/{memory_id}/promote",
    response_model=APIResponse[MemoryResponseSchema],
    summary="Promote a high-value memory",
)
async def promote_memory(
    memory_id: UUID,
    service: MemoryIntelligenceService = MemoryIntelligenceServiceDep,
    user_id: UUID = Query(..., description="Owner of the memory"),
) -> APIResponse[MemoryResponseSchema]:
    result = await service.promote_memory(memory_id, user_id=user_id)
    return _ok(MemoryResponseSchema.from_dto(result))


@router.post(
    "/{memory_id}/archive",
    response_model=APIResponse[MemoryResponseSchema],
    summary="Archive a low-value, idle memory",
)
async def archive_memory(
    memory_id: UUID,
    service: MemoryIntelligenceService = MemoryIntelligenceServiceDep,
    user_id: UUID = Query(..., description="Owner of the memory"),
    force: bool = Query(default=False, description="Archive even if criteria are not met"),
) -> APIResponse[MemoryResponseSchema]:
    result = await service.archive_memory(memory_id, user_id=user_id, force=force)
    return _ok(MemoryResponseSchema.from_dto(result))


@router.post(
    "/{memory_id}/restore",
    response_model=APIResponse[MemoryResponseSchema],
    summary="Restore an archived memory to ACTIVE",
)
async def restore_memory(
    memory_id: UUID,
    service: MemoryIntelligenceService = MemoryIntelligenceServiceDep,
    user_id: UUID = Query(..., description="Owner of the memory"),
) -> APIResponse[MemoryResponseSchema]:
    result = await service.restore_memory(memory_id, user_id=user_id)
    return _ok(MemoryResponseSchema.from_dto(result))
