"""Stage 19.1/19.2 — RBAC policy and tenant-isolation tests.

Pure policy tests over the authorization functions: role gating, admin
cross-tenant reach, and (critically) that USER/SERVICE principals cannot escape
their own tenant — the privilege-escalation / tenant-escape proofs.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.dto.auth_dto import AuthPrincipal
from app.application.exceptions import AuthorizationError, ResourceNotFoundForCaller
from app.application.services.authorization import (
    authorize_owner,
    require_role,
    resolve_scope,
)
from app.domain.value_objects.role import Role


def _principal(role: Role) -> AuthPrincipal:
    uid = uuid4()
    return AuthPrincipal(user_id=uid, tenant_id=uid, role=role)


# --- require_role ----------------------------------------------------------

def test_require_role_noop_without_principal() -> None:
    # Auth disabled (no principal) -> never raises (preserves pre-RBAC behavior).
    require_role(None, Role.ADMIN)


def test_require_role_allows_matching_and_admin() -> None:
    require_role(_principal(Role.USER), Role.USER)
    require_role(_principal(Role.SERVICE), Role.SERVICE, Role.USER)
    # ADMIN satisfies any gate (superset of every role's reach).
    require_role(_principal(Role.ADMIN), Role.SERVICE)


def test_require_role_rejects_insufficient_role() -> None:
    with pytest.raises(AuthorizationError):
        require_role(_principal(Role.USER), Role.ADMIN)
    with pytest.raises(AuthorizationError):
        require_role(_principal(Role.SERVICE), Role.ADMIN)


# --- resolve_scope: tenant isolation ---------------------------------------

def test_user_confined_to_own_scope() -> None:
    p = _principal(Role.USER)
    assert resolve_scope(p, None) == p.user_id          # default to own
    assert resolve_scope(p, p.user_id) == p.user_id     # own explicit scope ok


def test_user_cannot_escape_to_another_tenant() -> None:
    p = _principal(Role.USER)
    other = uuid4()
    with pytest.raises(AuthorizationError):
        resolve_scope(p, other)  # cross-tenant attempt -> 403


def test_service_cannot_escape_to_another_tenant() -> None:
    # SERVICE is not ADMIN: it has no cross-tenant reach.
    p = _principal(Role.SERVICE)
    with pytest.raises(AuthorizationError):
        resolve_scope(p, uuid4())


def test_admin_may_target_any_tenant() -> None:
    admin = _principal(Role.ADMIN)
    other = uuid4()
    assert resolve_scope(admin, other) == other         # honored as-is
    assert resolve_scope(admin, None) == admin.user_id   # falls back to own


def test_no_principal_passes_scope_through() -> None:
    other = uuid4()
    assert resolve_scope(None, other) == other
    assert resolve_scope(None, None) is None


# --- authorize_owner -------------------------------------------------------

def test_owner_check_blocks_non_owner_user() -> None:
    p = _principal(Role.USER)
    with pytest.raises(ResourceNotFoundForCaller):
        authorize_owner(p, uuid4())  # someone else's resource -> 404
    authorize_owner(p, p.user_id)    # own resource -> ok


def test_owner_check_bypassed_for_admin() -> None:
    admin = _principal(Role.ADMIN)
    authorize_owner(admin, uuid4())  # admin reaches any owner's resource


def test_principal_is_admin_flag() -> None:
    assert _principal(Role.ADMIN).is_admin is True
    assert _principal(Role.USER).is_admin is False
    assert _principal(Role.SERVICE).is_admin is False
