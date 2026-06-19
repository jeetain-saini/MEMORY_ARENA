"""Retrieval API endpoints (API v1).

Thin HTTP adapters over the MemoryRetrievalService. ``/search`` returns the
ranked top_k; ``/debug`` returns the full reranked candidate set with per-signal
score breakdowns (vector, bm25, memory, recency, final).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.dependencies.providers import MemoryRetrievalServiceDep
from app.application.services.retrieval.retrieval_service import MemoryRetrievalService
from app.core.logging import get_request_id
from app.schemas.responses import APIResponse
from app.schemas.retrieval import RetrievalResultSchema, RetrievalSearchRequestSchema

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post(
    "/search",
    response_model=APIResponse[RetrievalResultSchema],
    summary="Hybrid retrieval: vector + BM25 + memory + recency, reranked",
)
async def search(
    payload: RetrievalSearchRequestSchema,
    service: MemoryRetrievalService = MemoryRetrievalServiceDep,
) -> APIResponse[RetrievalResultSchema]:
    result = await service.search(payload.to_query())
    return APIResponse(data=RetrievalResultSchema.from_dto(result), request_id=get_request_id())


@router.post(
    "/debug",
    response_model=APIResponse[RetrievalResultSchema],
    summary="Retrieval with full per-signal score breakdown for every candidate",
)
async def debug(
    payload: RetrievalSearchRequestSchema,
    service: MemoryRetrievalService = MemoryRetrievalServiceDep,
) -> APIResponse[RetrievalResultSchema]:
    result = await service.debug(payload.to_query())
    return APIResponse(data=RetrievalResultSchema.from_dto(result), request_id=get_request_id())
