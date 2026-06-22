"""Integration: memory extraction runs cost-free (deterministic) even when the
answer provider is NVIDIA — i.e. extraction never calls NVIDIA.

Builds the real workflow engine via the factory with LLM_PROVIDER=nvidia and
EXTRACTION_LLM_PROVIDER=deterministic, then extracts the verification sentences.
A NVIDIA dependency would require a network call / API key; the deterministic
engine returns memories with no I/O.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

import pytest  # noqa: E402

from app.application.dto.extraction_dto import ExtractionRequest  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.infrastructure.llm.graphs.factory import build_workflow_engine  # noqa: E402
from app.infrastructure.llm.graphs.sequential_engine import (  # noqa: E402
    SequentialExtractionEngine,
)
from app.infrastructure.llm.providers.deterministic_provider import (  # noqa: E402
    DeterministicLLMProvider,
)
from app.infrastructure.llm.providers.factory import (  # noqa: E402
    build_extraction_llm_provider,
    build_llm_provider,
)
from uuid import uuid4  # noqa: E402


def _clear() -> None:
    get_settings.cache_clear()
    build_llm_provider.cache_clear()
    build_extraction_llm_provider.cache_clear()
    build_workflow_engine.cache_clear()


def test_extraction_uses_deterministic_with_nvidia_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "a-sufficiently-long-secret")
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")          # answers -> NVIDIA
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-test")
    monkeypatch.setenv("LLM_MODEL", "minimaxai/minimax-m3")
    monkeypatch.delenv("EXTRACTION_LLM_PROVIDER", raising=False)  # default deterministic
    monkeypatch.setenv("WORKFLOW_ENGINE", "sequential")
    _clear()
    try:
        engine = build_workflow_engine()
        assert isinstance(engine, SequentialExtractionEngine)
        # The engine's provider is the deterministic (local, free) one.
        assert isinstance(engine._provider, DeterministicLLMProvider)

        sentences = [
            "My name is Jeetain.",
            "I am learning LangGraph and LangChain.",
            "I prefer dark mode.",
            "I use PostgreSQL.",
        ]
        user = uuid4()
        extracted: dict[str, MemoryType] = {}
        for text in sentences:
            result = asyncio.run(
                engine.extract_memories(ExtractionRequest(user_id=user, raw_text=text))
            )
            assert result.memories, f"no memory extracted from {text!r}"
            mem = result.memories[0]
            # Content is preserved verbatim (the sentence body).
            assert text.split(".")[0].lower() in mem.content.lower()
            extracted[text] = mem.memory_type
        # The rule-based classifier types "prefer ..." as a PREFERENCE.
        assert extracted["I prefer dark mode."] == MemoryType.PREFERENCE
    finally:
        _clear()
