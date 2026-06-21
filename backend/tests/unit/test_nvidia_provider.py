"""Unit tests for NvidiaProvider (NVIDIA NIM via ChatNVIDIA).

A fake ChatNVIDIA-like client is injected so no network call is made and the
ChatNVIDIA / langchain-nvidia-ai-endpoints package is not required. The fake
captures the messages it was invoked with so message construction is asserted.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

import pytest  # noqa: E402

from app.infrastructure.llm.providers.nvidia_provider import NvidiaProvider  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChatNVIDIA:
    """Records the last ainvoke messages and returns a canned response."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_messages: list[tuple[str, str]] | None = None

    async def ainvoke(self, messages):
        self.last_messages = messages
        return _FakeMessage(self.reply)


def test_model_name_returns_configured_model() -> None:
    provider = NvidiaProvider(api_key="k", model="meta/llama-3.1-8b-instruct", client=_FakeChatNVIDIA(""))
    assert provider.model_name == "meta/llama-3.1-8b-instruct"


def test_generate_returns_content_and_builds_system_and_human_messages() -> None:
    fake = _FakeChatNVIDIA("FastAPI is a Python web framework.")
    provider = NvidiaProvider(api_key="k", model="m", client=fake)
    out = _run(provider.generate("What is FastAPI?", system="You are helpful."))
    assert out == "FastAPI is a Python web framework."
    assert fake.last_messages == [("system", "You are helpful."), ("human", "What is FastAPI?")]


def test_generate_without_system_only_human_message() -> None:
    fake = _FakeChatNVIDIA("hello")
    provider = NvidiaProvider(api_key="k", model="m", client=fake)
    out = _run(provider.generate("hi"))
    assert out == "hello"
    assert fake.last_messages == [("human", "hi")]


def test_generate_coerces_non_string_content() -> None:
    fake = _FakeChatNVIDIA(reply=None)  # type: ignore[arg-type]
    fake.reply = ["a", "b"]  # non-string content (e.g. multimodal blocks)
    provider = NvidiaProvider(api_key="k", model="m", client=fake)
    out = _run(provider.generate("x"))
    assert isinstance(out, str)


def test_structured_generate_parses_json_into_schema_keys() -> None:
    fake = _FakeChatNVIDIA('{"memory_type": "fact", "importance": 0.7}')
    provider = NvidiaProvider(api_key="k", model="m", client=fake)
    out = _run(provider.structured_generate("x", schema={"memory_type": "str", "importance": "float"}))
    assert out == {"memory_type": "fact", "importance": 0.7}
    # The JSON instruction is appended to the system message.
    assert fake.last_messages is not None
    assert fake.last_messages[0][0] == "system"
    assert "JSON object" in fake.last_messages[0][1]


def test_structured_generate_invalid_json_yields_none_for_each_key() -> None:
    fake = _FakeChatNVIDIA("not json at all")
    provider = NvidiaProvider(api_key="k", model="m", client=fake)
    out = _run(provider.structured_generate("x", schema={"a": "str", "b": "float"}))
    assert out == {"a": None, "b": None}


def test_health_check_reflects_api_key_presence() -> None:
    assert _run(NvidiaProvider(api_key="k", model="m", client=_FakeChatNVIDIA("")).health_check()) is True
    assert _run(NvidiaProvider(api_key=None, model="m", client=_FakeChatNVIDIA("")).health_check()) is False


def test_factory_selects_nvidia_provider_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.infrastructure.llm.providers.factory import build_llm_provider

    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-test-key")
    monkeypatch.setenv("LLM_MODEL", "meta/llama-3.1-8b-instruct")
    get_settings.cache_clear()
    build_llm_provider.cache_clear()
    try:
        provider = build_llm_provider()
        assert isinstance(provider, NvidiaProvider)
        assert provider.model_name == "meta/llama-3.1-8b-instruct"
    finally:
        get_settings.cache_clear()
        build_llm_provider.cache_clear()
