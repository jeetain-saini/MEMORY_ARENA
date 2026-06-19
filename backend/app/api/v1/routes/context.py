"""Context Assembly API endpoints (API v1).

``/build`` returns the assembled ContextPackage; ``/debug`` returns the package
plus full provenance (selected, dropped, conflicts, consolidations, compression
stats). No LLM calls — context construction only.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.dependencies.providers import ContextBuilderServiceDep
from app.application.services.context.context_builder import ContextBuilderService
from app.core.logging import get_request_id
from app.schemas.context import (
    ContextDebugSchema,
    ContextPackageSchema,
    ContextRequestSchema,
)
from app.schemas.responses import APIResponse

router = APIRouter(prefix="/context", tags=["context"])


@router.post(
    "/build",
    response_model=APIResponse[ContextPackageSchema],
    summary="Assemble a token-budgeted context package",
)
async def build_context(
    payload: ContextRequestSchema,
    service: ContextBuilderService = ContextBuilderServiceDep,
) -> APIResponse[ContextPackageSchema]:
    package = await service.build(payload.to_request())
    return APIResponse(data=ContextPackageSchema.from_dto(package), request_id=get_request_id())


@router.post(
    "/debug",
    response_model=APIResponse[ContextDebugSchema],
    summary="Context assembly with full provenance for inspection",
)
async def debug_context(
    payload: ContextRequestSchema,
    service: ContextBuilderService = ContextBuilderServiceDep,
) -> APIResponse[ContextDebugSchema]:
    debug = await service.debug(payload.to_request())
    return APIResponse(data=ContextDebugSchema.from_dto(debug), request_id=get_request_id())
