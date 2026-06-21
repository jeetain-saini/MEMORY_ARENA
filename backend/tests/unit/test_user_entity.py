"""Unit tests for the User domain entity, focused on the tenant invariant."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.domain.entities.user import User
from app.domain.exceptions.errors import DomainError


def test_tenant_id_defaults_to_own_id() -> None:
    user = User(email="a@example.com")
    assert user.tenant_id == user.id


def test_explicit_tenant_id_is_kept() -> None:
    tenant = uuid4()
    user = User(email="a@example.com", tenant_id=tenant)
    assert user.tenant_id == tenant


def test_register_makes_user_its_own_tenant() -> None:
    user = User.register(email="A@Example.com", password_hash="h")
    assert user.email == "a@example.com"
    assert user.tenant_id == user.id


def test_empty_email_rejected() -> None:
    with pytest.raises(DomainError):
        User(email="   ")


def test_can_authenticate_requires_active_and_hash() -> None:
    assert User(email="a@example.com", password_hash="h").can_authenticate is True
    assert User(email="a@example.com", password_hash=None).can_authenticate is False
    assert User(email="a@example.com", password_hash="h", is_active=False).can_authenticate is False
