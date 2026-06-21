"""Unit tests for the pure authorization policy (Stage 14 Phase 3)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.dto.auth_dto import AuthPrincipal
from app.application.exceptions import AuthorizationError, ResourceNotFoundForCaller
from app.application.services.authorization import authorize_owner, resolve_scope


def _principal(user_id=None) -> AuthPrincipal:
    uid = user_id or uuid4()
    return AuthPrincipal(user_id=uid, tenant_id=uid)


# --- no principal (auth disabled): everything passes through ---------------

def test_resolve_scope_passthrough_when_no_principal() -> None:
    target = uuid4()
    assert resolve_scope(None, target) == target
    assert resolve_scope(None, None) is None


def test_authorize_owner_noop_when_no_principal() -> None:
    authorize_owner(None, uuid4())  # does not raise


# --- resolve_scope with a principal ----------------------------------------

def test_resolve_scope_defaults_to_principal_when_unspecified() -> None:
    principal = _principal()
    assert resolve_scope(principal, None) == principal.user_id


def test_resolve_scope_allows_matching_user() -> None:
    principal = _principal()
    assert resolve_scope(principal, principal.user_id) == principal.user_id


def test_resolve_scope_rejects_other_user() -> None:
    principal = _principal()
    with pytest.raises(AuthorizationError):
        resolve_scope(principal, uuid4())


# --- authorize_owner with a principal --------------------------------------

def test_authorize_owner_allows_owner() -> None:
    principal = _principal()
    authorize_owner(principal, principal.user_id)  # does not raise


def test_authorize_owner_rejects_non_owner_as_not_found() -> None:
    principal = _principal()
    with pytest.raises(ResourceNotFoundForCaller):
        authorize_owner(principal, uuid4())
