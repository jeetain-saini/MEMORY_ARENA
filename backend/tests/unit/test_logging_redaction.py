"""Unit tests for sensitive-field redaction in the JSON log formatter (Stage 14)."""

from __future__ import annotations

import json
import logging

from app.core.logging import _REDACTED, JsonFormatter


def _format(msg: str, **extra) -> dict:
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_sensitive_extra_keys_are_redacted() -> None:
    out = _format(
        "auth event",
        password="hunter2",
        access_token="abc.def.ghi",
        refresh_token="r-123",
        authorization="Bearer xyz",
        api_key="sk-live-123",
    )
    for key in ("password", "access_token", "refresh_token", "authorization", "api_key"):
        assert out[key] == _REDACTED


def test_newly_added_sensitive_keys_are_redacted() -> None:
    out = _format(
        "secrets",
        client_secret="cs-1",
        private_key="-----BEGIN-----",
        session="s-1",
        session_id="sid-1",
    )
    assert out["client_secret"] == _REDACTED
    assert out["private_key"] == _REDACTED
    assert out["session"] == _REDACTED
    assert out["session_id"] == _REDACTED


def test_x_api_key_substring_match() -> None:
    out = _format("event", **{"x-api-key": "k-1"})
    assert out["x-api-key"] == _REDACTED


def test_nested_dict_is_redacted_recursively() -> None:
    out = _format("event", context={"token": "t-1", "user": "alice", "nested": {"secret": "s"}})
    assert out["context"]["token"] == _REDACTED
    assert out["context"]["user"] == "alice"
    assert out["context"]["nested"]["secret"] == _REDACTED


def test_bearer_token_in_message_is_redacted() -> None:
    out = _format("Authenticated with Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert "eyJhbGci" not in out["message"]
    assert f"Bearer {_REDACTED}" in out["message"]


def test_non_sensitive_fields_pass_through() -> None:
    out = _format("request.finish", method="GET", path="/api/v1/memories", status_code=200)
    assert out["method"] == "GET"
    assert out["path"] == "/api/v1/memories"
    assert out["status_code"] == 200


def test_mixed_payload_redacts_only_sensitive() -> None:
    out = _format("event", user_id="u-123", access_token="a.b.c", status_code=200)
    assert out["user_id"] == "u-123"        # preserved
    assert out["status_code"] == 200         # preserved
    assert out["access_token"] == _REDACTED  # redacted


def test_redaction_is_idempotent() -> None:
    # A value already equal to the placeholder, and an already-redacted message,
    # must remain unchanged after another pass.
    out = _format(f"Bearer {_REDACTED}", access_token=_REDACTED)
    assert out["access_token"] == _REDACTED
    assert out["message"] == f"Bearer {_REDACTED}"
    assert out["message"].count(_REDACTED) == 1


def test_output_is_valid_single_line_json() -> None:
    formatted = JsonFormatter().format(
        logging.LogRecord(
            name="t", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello", args=(), exc_info=None,
        )
    )
    assert "\n" not in formatted
    json.loads(formatted)  # does not raise
