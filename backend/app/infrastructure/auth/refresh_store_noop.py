"""NoOpRefreshTokenStore — inert refresh store.

The safe default when ``AUTH_ENABLED`` is false: nothing is persisted and every
lookup is empty, so the app starts without requiring Redis. (The ``/auth``
endpoints are themselves disabled when auth is off, so this is never exercised
through the API — it is defense-in-depth for the composition root.)
"""

from __future__ import annotations

from app.application.dto.auth_dto import RefreshRecord, RotationOutcome, RotationState
from app.application.interfaces.refresh_token_store import RefreshTokenStore


class NoOpRefreshTokenStore(RefreshTokenStore):
    async def save(self, record: RefreshRecord) -> None:
        return None

    async def consume_for_rotation(self, token_id: str) -> RotationOutcome:
        return RotationOutcome(RotationState.NOT_FOUND)

    async def revoke_family(self, family_id: str) -> None:
        return None

    async def family_of(self, token_id: str) -> str | None:
        return None
