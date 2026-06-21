"""Auth adapter factories — config-driven selection (Stage 14 Phase 2).

Mirrors the other infrastructure factories. The refresh-token store is the
flag-gated piece: a ``NoOpRefreshTokenStore`` when ``AUTH_ENABLED`` is false (so
the app needs no Redis at rest), the durable ``RedisRefreshTokenStore`` when auth
is enabled. The in-memory store is wired by tests via a provider override, the
established pattern for offline adapters.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.clock import Clock
from app.application.interfaces.password_hasher import PasswordHasher
from app.application.interfaces.refresh_token_store import RefreshTokenStore
from app.application.interfaces.token_service import TokenService
from app.core.config import get_settings
from app.infrastructure.auth.refresh_store_noop import NoOpRefreshTokenStore
from app.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher
from app.infrastructure.security.jwt_token_service import JwtTokenService


@lru_cache(maxsize=1)
def build_password_hasher() -> PasswordHasher:
    return BcryptPasswordHasher()


def build_token_service(clock: Clock) -> TokenService:
    settings = get_settings()
    return JwtTokenService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        access_ttl_seconds=settings.access_token_expire_minutes * 60,
        clock=clock,
    )


def build_refresh_token_store(clock: Clock) -> RefreshTokenStore:
    settings = get_settings()
    if not settings.auth_enabled:
        return NoOpRefreshTokenStore()
    # Lazy import so the Redis adapter (and client) is only touched when auth is on.
    from app.infrastructure.auth.refresh_store_redis import RedisRefreshTokenStore
    from app.infrastructure.cache.redis import redis_manager

    return RedisRefreshTokenStore(
        redis_manager.client,
        clock,
        family_ttl_seconds=settings.refresh_token_expire_days * 86400,
    )
