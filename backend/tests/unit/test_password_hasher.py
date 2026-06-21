"""Unit tests for BcryptPasswordHasher (Stage 14 Phase 2)."""

from __future__ import annotations

from app.infrastructure.security.bcrypt_hasher import BcryptPasswordHasher

# Low cost factor keeps the suite fast; production uses the default.
_HASHER = BcryptPasswordHasher(rounds=4)


def test_hash_is_not_plaintext_and_verifies() -> None:
    digest = _HASHER.hash("correct horse battery staple")
    assert digest != "correct horse battery staple"
    assert _HASHER.verify("correct horse battery staple", digest) is True


def test_wrong_password_does_not_verify() -> None:
    digest = _HASHER.hash("s3cret")
    assert _HASHER.verify("guess", digest) is False


def test_hashes_are_salted_and_differ() -> None:
    assert _HASHER.hash("same") != _HASHER.hash("same")


def test_verify_against_empty_or_malformed_hash_is_false() -> None:
    assert _HASHER.verify("anything", "") is False
    assert _HASHER.verify("anything", "not-a-bcrypt-hash") is False


def test_long_password_beyond_72_bytes_is_handled() -> None:
    pw = "a" * 200
    digest = _HASHER.hash(pw)
    assert _HASHER.verify(pw, digest) is True
