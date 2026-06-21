"""AuthService — registration, login, refresh rotation, and logout.

Orchestration facade (like ``MemoryService``): it owns no SQL or framework code,
only the auth workflow over its injected collaborators — a Unit-of-Work factory
(user persistence), a ``PasswordHasher``, a ``TokenService`` (access JWTs), a
``RefreshTokenStore`` (opaque rotating refresh tokens), and the ``Clock``.

Refresh tokens are opaque random strings; only their SHA-256 is stored. Rotation
goes through the store's single atomic ``consume_for_rotation`` contract, and a
``ROTATED`` result (reuse/replay of an already-consumed token) revokes the whole
family. All expiry math uses ``clock.now_epoch()``.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from uuid import UUID, uuid4

from app.application.dto.auth_dto import (
    AuthIdentity,
    Credentials,
    RefreshRecord,
    RegisterCommand,
    RotationState,
    TokenPair,
)
from app.application.exceptions import AuthenticationError, EmailAlreadyRegisteredError
from app.application.interfaces.clock import Clock
from app.application.interfaces.password_hasher import PasswordHasher
from app.application.interfaces.refresh_token_store import RefreshTokenStore
from app.application.interfaces.token_service import TokenService
from app.application.interfaces.unit_of_work import UnitOfWork
from app.domain.entities.user import User

_REFRESH_BYTES = 48


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        hasher: PasswordHasher,
        token_service: TokenService,
        refresh_store: RefreshTokenStore,
        clock: Clock,
        *,
        refresh_ttl_seconds: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._tokens = token_service
        self._refresh = refresh_store
        self._clock = clock
        self._refresh_ttl = refresh_ttl_seconds

    async def register(self, command: RegisterCommand) -> AuthIdentity:
        email = command.email.strip().lower()
        async with self._uow_factory() as uow:
            if await uow.users.get_by_email(email) is not None:
                raise EmailAlreadyRegisteredError(email)
            user = User.register(
                email=email,
                password_hash=self._hasher.hash(command.password),
                display_name=command.display_name,
            )
            await uow.users.add(user)
            await uow.commit()
        return AuthIdentity(user_id=user.id, email=user.email)

    async def login(self, credentials: Credentials) -> TokenPair:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(credentials.email)
        # Generic failure regardless of which factor failed (no user enumeration).
        if user is None or not user.can_authenticate:
            raise AuthenticationError()
        if not self._hasher.verify(credentials.password, user.password_hash or ""):
            raise AuthenticationError()
        return await self._issue_pair(user.id, family_id=uuid4().hex)

    async def refresh(self, refresh_token: str) -> TokenPair:
        token_id = _hash_token(refresh_token)
        outcome = await self._refresh.consume_for_rotation(token_id)
        if outcome.state is RotationState.VALID and outcome.user_id is not None:
            return await self._issue_pair(outcome.user_id, family_id=outcome.family_id or uuid4().hex)
        if outcome.state is RotationState.ROTATED and outcome.family_id is not None:
            # Reuse/replay of a consumed token -> revoke the whole family.
            await self._refresh.revoke_family(outcome.family_id)
        raise AuthenticationError()

    async def logout(self, refresh_token: str) -> None:
        # Idempotent: revoke the token's family if we can find it; never error.
        family_id = await self._refresh.family_of(_hash_token(refresh_token))
        if family_id is not None:
            await self._refresh.revoke_family(family_id)

    async def _issue_pair(self, user_id: UUID, *, family_id: str) -> TokenPair:
        access = self._tokens.issue_access(user_id)
        raw_refresh = secrets.token_urlsafe(_REFRESH_BYTES)
        record = RefreshRecord(
            token_id=_hash_token(raw_refresh),
            family_id=family_id,
            user_id=user_id,
            expires_at=self._clock.now_epoch() + self._refresh_ttl,
            status="active",
        )
        await self._refresh.save(record)
        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,
            expires_in=self._tokens.access_ttl_seconds,
        )
