"""JwtPrincipalProvider — the production PrincipalProvider adapter.

Resolves a bearer access token to an ``AuthPrincipal`` by composing the Phase 2
``TokenService`` (decode/verify) with a ``UserRepository`` load (to obtain the
tenant and confirm the account is still active). It holds no JWT specifics of its
own — it delegates decoding to the ``TokenService`` port — so swapping the token
scheme never touches this adapter's structure.

Any failure (missing/invalid/expired token, unknown or inactive user) raises
``AuthenticationError`` (mapped to 401), so a token for a deactivated account is
rejected even though it has not yet expired.
"""

from __future__ import annotations

from collections.abc import Callable

from app.application.dto.auth_dto import AuthPrincipal
from app.application.exceptions import AuthenticationError
from app.application.interfaces.principal_provider import PrincipalProvider
from app.application.interfaces.token_service import TokenService
from app.application.interfaces.unit_of_work import UnitOfWork


class JwtPrincipalProvider(PrincipalProvider):
    def __init__(
        self, token_service: TokenService, uow_factory: Callable[[], UnitOfWork]
    ) -> None:
        self._tokens = token_service
        self._uow_factory = uow_factory

    async def get_principal(self, token: str | None) -> AuthPrincipal:
        if not token:
            raise AuthenticationError("Missing bearer token")
        claims = self._tokens.decode_access(token)  # raises AuthenticationError
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(claims.user_id)
        if user is None or not user.is_active or user.tenant_id is None:
            raise AuthenticationError()
        return AuthPrincipal(user_id=user.id, tenant_id=user.tenant_id)
