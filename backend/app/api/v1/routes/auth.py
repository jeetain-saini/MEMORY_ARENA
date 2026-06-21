"""Authentication API endpoints (API v1, Stage 14 Phase 2).

``POST /auth/register | /auth/login | /auth/refresh | /auth/logout``.

The whole router is gated by ``require_auth_enabled``: when ``AUTH_ENABLED`` is
false (the default) every endpoint returns 404, so the auth surface is invisible
and existing clients/tests are unaffected. Enforcement of auth on *other*
endpoints is Phase 3; Phase 2 only provides identity + token issuance/rotation.

Thin adapters: validate via schemas, delegate to ``AuthService``, wrap in the
standard ``APIResponse`` envelope. The service raises framework-free errors
(``AuthenticationError`` -> 401, ``EmailAlreadyRegisteredError`` -> 409) mapped
centrally in core exception handlers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.v1.dependencies.providers import AuthServiceDep, require_auth_enabled
from app.application.services.auth.auth_service import AuthService
from app.core.logging import get_request_id
from app.schemas.auth import (
    LoginRequestSchema,
    RefreshRequestSchema,
    RegisterRequestSchema,
    RegisterResponseSchema,
    TokenResponseSchema,
)
from app.schemas.responses import APIResponse

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(require_auth_enabled)])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=APIResponse[RegisterResponseSchema],
    summary="Register a new account",
)
async def register(
    payload: RegisterRequestSchema,
    service: AuthService = AuthServiceDep,
) -> APIResponse[RegisterResponseSchema]:
    identity = await service.register(payload.to_command())
    return APIResponse(
        data=RegisterResponseSchema(user_id=identity.user_id, email=identity.email),
        request_id=get_request_id(),
    )


@router.post(
    "/login",
    response_model=APIResponse[TokenResponseSchema],
    summary="Log in and receive an access + refresh token pair",
)
async def login(
    payload: LoginRequestSchema,
    service: AuthService = AuthServiceDep,
) -> APIResponse[TokenResponseSchema]:
    pair = await service.login(payload.to_credentials())
    return APIResponse(data=TokenResponseSchema.from_dto(pair), request_id=get_request_id())


@router.post(
    "/refresh",
    response_model=APIResponse[TokenResponseSchema],
    summary="Rotate a refresh token for a new token pair",
)
async def refresh(
    payload: RefreshRequestSchema,
    service: AuthService = AuthServiceDep,
) -> APIResponse[TokenResponseSchema]:
    pair = await service.refresh(payload.refresh_token)
    return APIResponse(data=TokenResponseSchema.from_dto(pair), request_id=get_request_id())


@router.post(
    "/logout",
    response_model=APIResponse[dict[str, bool]],
    summary="Revoke a refresh token's family (logout)",
)
async def logout(
    payload: RefreshRequestSchema,
    service: AuthService = AuthServiceDep,
) -> APIResponse[dict[str, bool]]:
    await service.logout(payload.refresh_token)
    return APIResponse(data={"logged_out": True}, request_id=get_request_id())
