"""Unit tests for the refresh-token stores (in-memory + no-op).

Covers the atomic ``consume_for_rotation`` contract states: VALID, ROTATED
(reuse), REVOKED, EXPIRED, NOT_FOUND.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.auth_dto import RefreshRecord, RotationState
from app.application.services.observability.frozen_clock import FrozenClock
from app.infrastructure.auth.refresh_store_memory import InMemoryRefreshTokenStore
from app.infrastructure.auth.refresh_store_noop import NoOpRefreshTokenStore


def _run(coro):
    return asyncio.run(coro)


def _record(token_id: str, family: str, *, user_id=None, expires_at: float = 5000.0) -> RefreshRecord:
    return RefreshRecord(
        token_id=token_id,
        family_id=family,
        user_id=user_id or uuid4(),
        expires_at=expires_at,
        status="active",
    )


def _store(epoch: float = 1000.0) -> InMemoryRefreshTokenStore:
    return InMemoryRefreshTokenStore(FrozenClock(epoch=epoch))


def test_consume_valid_then_reuse_is_rotated() -> None:
    store = _store()
    uid = uuid4()
    _run(store.save(_record("t1", "f1", user_id=uid)))

    first = _run(store.consume_for_rotation("t1"))
    assert first.state is RotationState.VALID
    assert first.user_id == uid
    assert first.family_id == "f1"

    # Replaying the now-consumed token is reuse.
    second = _run(store.consume_for_rotation("t1"))
    assert second.state is RotationState.ROTATED
    assert second.family_id == "f1"


def test_consume_missing_is_not_found() -> None:
    assert _run(_store().consume_for_rotation("nope")).state is RotationState.NOT_FOUND


def test_consume_expired() -> None:
    store = _store(epoch=1000.0)
    _run(store.save(_record("t2", "f2", expires_at=1500.0)))
    store._clock.advance(600)  # now 1600 >= 1500
    assert _run(store.consume_for_rotation("t2")).state is RotationState.EXPIRED


def test_consume_revoked_family() -> None:
    store = _store()
    _run(store.save(_record("t3", "f3")))
    _run(store.revoke_family("f3"))
    assert _run(store.consume_for_rotation("t3")).state is RotationState.REVOKED


def test_family_of() -> None:
    store = _store()
    _run(store.save(_record("t4", "f4")))
    assert _run(store.family_of("t4")) == "f4"
    assert _run(store.family_of("missing")) is None


def test_noop_store_is_inert() -> None:
    store = NoOpRefreshTokenStore()
    _run(store.save(_record("t", "f")))
    assert _run(store.consume_for_rotation("t")).state is RotationState.NOT_FOUND
    assert _run(store.family_of("t")) is None
    _run(store.revoke_family("f"))  # no error
