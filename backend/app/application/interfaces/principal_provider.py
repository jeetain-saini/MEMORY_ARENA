"""PrincipalProvider port — resolves a request's authenticated principal.

Given a bearer token (or ``None``), produce the ``AuthPrincipal`` the
application layer authorizes against. The application/composition root depends on
this abstraction, never on JWT/decoding specifics — those live in an
infrastructure adapter (``JwtPrincipalProvider``).

Contract: a valid token for an active user yields an ``AuthPrincipal``; a
missing/invalid/expired token, or a missing/inactive user, raises
``AuthenticationError`` (mapped to 401). Returning ``None`` is reserved for an
adapter that represents "no authentication" — the JWT adapter never returns
``None`` (the AUTH_ENABLED gate is handled by the API dependency, not here).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.dto.auth_dto import AuthPrincipal


class PrincipalProvider(ABC):
    @abstractmethod
    async def get_principal(self, token: str | None) -> AuthPrincipal | None:
        """Resolve the principal for a bearer ``token`` (raises on auth failure)."""
