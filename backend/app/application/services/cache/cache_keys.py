"""Deterministic cache keys + the keys to invalidate on a memory mutation.

Per-user and global variants are cached (approved decision); a write invalidates
the writer's user key **and** the global key (broad, correctness-first). Keys are
namespaced by resource so invalidation is exact (no prefix scan needed on the
common path).
"""

from __future__ import annotations

from uuid import UUID

_GLOBAL = "global"


def _scope(user_id: UUID | None) -> str:
    return f"user:{user_id}" if user_id is not None else _GLOBAL


def analytics_key(user_id: UUID | None) -> str:
    return f"analytics:{_scope(user_id)}"


def health_key(user_id: UUID | None) -> str:
    return f"health:{_scope(user_id)}"


def invalidation_keys(user_id: UUID) -> list[str]:
    """Keys to delete when ``user_id``'s memories change (user + global, both resources)."""
    return [
        analytics_key(user_id),
        analytics_key(None),
        health_key(user_id),
        health_key(None),
    ]
