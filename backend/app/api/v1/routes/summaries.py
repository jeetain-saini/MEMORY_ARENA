"""Memory summary read endpoints (API v1).

Thin presentation-layer adapters over the existing summarization stack:

* ``GET /summaries/{user_id}``                — all rolling summaries for a tenant
* ``GET /summaries/{user_id}?scope=<type>``   — optional filter to one scope
* ``GET /summaries/{user_id}/{scope}``        — a single scope's summary (404 if absent)

No business logic: reads delegate to ``MemorySummaryService``, which delegates to
``MemorySummaryRepository``. Summaries are derived artifacts produced by the
Stage 11 maintenance workflow; nothing is generated or mutated here.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.v1.dependencies.providers import SummaryServiceDep
from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.core.exceptions import AppException
from app.core.logging import get_request_id
from app.domain.value_objects.memory_type import MemoryType
from app.schemas.responses import APIResponse
from app.schemas.summary import MemorySummarySchema

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get(
    "/{user_id}",
    response_model=APIResponse[list[MemorySummarySchema]],
    summary="List a user's rolling memory summaries (optionally filtered by scope)",
)
async def list_summaries(
    user_id: UUID,
    service: MemorySummaryService = SummaryServiceDep,
    scope: MemoryType | None = Query(default=None, description="Optional scope filter"),
) -> APIResponse[list[MemorySummarySchema]]:
    if scope is not None:
        summary = await service.get(user_id, scope)
        summaries = [summary] if summary is not None else []
    else:
        summaries = await service.list_for_user(user_id)
    return APIResponse(
        data=[MemorySummarySchema.from_dto(s) for s in summaries],
        request_id=get_request_id(),
    )


@router.get(
    "/{user_id}/{scope}",
    response_model=APIResponse[MemorySummarySchema],
    summary="Get a single scope's rolling summary for a user",
)
async def get_summary(
    user_id: UUID,
    scope: MemoryType,
    service: MemorySummaryService = SummaryServiceDep,
) -> APIResponse[MemorySummarySchema]:
    summary = await service.get(user_id, scope)
    if summary is None:
        raise AppException(
            f"No {scope.value} summary for user {user_id}",
            error_code="summary_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return APIResponse(data=MemorySummarySchema.from_dto(summary), request_id=get_request_id())
