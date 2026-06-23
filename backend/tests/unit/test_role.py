"""Unit tests for the RBAC Role value object (Stage 19.1)."""

from __future__ import annotations

from app.domain.value_objects.role import Role


def test_known_roles_parse() -> None:
    assert Role.from_str("user") is Role.USER
    assert Role.from_str("admin") is Role.ADMIN
    assert Role.from_str("service") is Role.SERVICE
    assert Role.from_str("ADMIN") is Role.ADMIN  # case-insensitive


def test_absent_or_unknown_defaults_to_user() -> None:
    # Tokens/rows minted before 19.1 carry no role -> least privilege.
    assert Role.from_str(None) is Role.USER
    assert Role.from_str("") is Role.USER
    assert Role.from_str("superuser") is Role.USER


def test_is_admin_flag() -> None:
    assert Role.ADMIN.is_admin is True
    assert Role.USER.is_admin is False
    assert Role.SERVICE.is_admin is False


def test_role_is_str_valued() -> None:
    # str-enum so it serializes cleanly into JWT claims / DB columns.
    assert Role.USER.value == "user"
    assert str(Role.ADMIN.value) == "admin"
