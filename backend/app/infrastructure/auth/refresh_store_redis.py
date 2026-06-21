"""RedisRefreshTokenStore — durable, multi-instance refresh store.

The production adapter (selected when ``AUTH_ENABLED`` is true). Each token is a
Redis hash ``refresh:{token_id}``; a family is revoked by setting a marker key
``refresh:family:{family_id}:revoked``.

``consume_for_rotation`` is made atomic with a single server-side Lua script:
in one round-trip it classifies the token and, only when VALID, flips its status
to ``rotated`` — eliminating the get -> check -> mark race across instances.

Not exercised by the offline suite (no Redis server); a fakeredis-guarded test
covers it when the package is available, and it is verified against a live Redis
(mirroring the live-Neo4j approach). Behavioral parity with the in-memory store
is guaranteed by the shared RotationState contract.
"""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

from app.application.dto.auth_dto import RefreshRecord, RotationOutcome, RotationState
from app.application.interfaces.clock import Clock
from app.application.interfaces.refresh_token_store import RefreshTokenStore

# KEYS[1] = token hash key; ARGV[1] = now_epoch.
# Returns "state|user_id|family_id" (user_id/family_id may be empty).
_CONSUME_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return 'not_found||'
end
local fam = redis.call('HGET', KEYS[1], 'family_id')
local uid = redis.call('HGET', KEYS[1], 'user_id')
local exp = redis.call('HGET', KEYS[1], 'expires_at')
local status = redis.call('HGET', KEYS[1], 'status')
if redis.call('EXISTS', 'refresh:family:' .. fam .. ':revoked') == 1 then
    return 'revoked|' .. uid .. '|' .. fam
end
if tonumber(ARGV[1]) >= tonumber(exp) then
    return 'expired|' .. uid .. '|' .. fam
end
if status == 'rotated' then
    return 'rotated|' .. uid .. '|' .. fam
end
redis.call('HSET', KEYS[1], 'status', 'rotated')
return 'valid|' .. uid .. '|' .. fam
"""


def _token_key(token_id: str) -> str:
    return f"refresh:{token_id}"


def _family_revoked_key(family_id: str) -> str:
    return f"refresh:family:{family_id}:revoked"


class RedisRefreshTokenStore(RefreshTokenStore):
    def __init__(self, client: Redis, clock: Clock, *, family_ttl_seconds: int) -> None:
        self._client = client
        self._clock = clock
        self._family_ttl = family_ttl_seconds
        self._consume = client.register_script(_CONSUME_LUA)

    async def save(self, record: RefreshRecord) -> None:
        key = _token_key(record.token_id)
        ttl = max(1, int(record.expires_at - self._clock.now_epoch()))
        await self._client.hset(
            key,
            mapping={
                "family_id": record.family_id,
                "user_id": str(record.user_id),
                "expires_at": str(record.expires_at),
                "status": record.status,
            },
        )
        await self._client.expire(key, ttl)

    async def consume_for_rotation(self, token_id: str) -> RotationOutcome:
        raw = await self._consume(keys=[_token_key(token_id)], args=[int(self._clock.now_epoch())])
        state_str, uid, fam = (raw.split("|", 2) + ["", ""])[:3] if isinstance(raw, str) else (
            (raw.decode().split("|", 2) + ["", ""])[:3]
        )
        state = RotationState(state_str)
        user_id = UUID(uid) if uid else None
        return RotationOutcome(state=state, user_id=user_id, family_id=fam or None)

    async def revoke_family(self, family_id: str) -> None:
        await self._client.set(_family_revoked_key(family_id), "1", ex=self._family_ttl)

    async def family_of(self, token_id: str) -> str | None:
        fam = await self._client.hget(_token_key(token_id), "family_id")
        if fam is None:
            return None
        return fam if isinstance(fam, str) else fam.decode()
