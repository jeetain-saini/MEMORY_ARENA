"""DeterministicLLMProvider — offline, reproducible LLM stand-in.

The dev/test default (mirrors the hash embedding provider). It produces stable,
rule-based answers for the structured operations the extraction workflow needs —
signal detection, candidate segmentation, type classification, and
importance/confidence estimation — so the whole pipeline runs without API keys
or network and tests are deterministic. It is **not** semantic.

It is generic over the requested ``schema`` keys; unknown keys yield ``None``.
"""

from __future__ import annotations

import re
from typing import Any

from app.application.interfaces.llm_provider import LLMProvider
from app.domain.value_objects.memory_type import MemoryType

_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")
_WORD = re.compile(r"[A-Za-z0-9']+")
_HEDGES = {"maybe", "might", "perhaps", "possibly", "think", "guess", "probably"}
_EMPHASIS = {"important", "critical", "always", "never", "must", "key", "essential"}

# Ordered, first-match-wins keyword rules for type classification.
_TYPE_RULES: list[tuple[MemoryType, set[str]]] = [
    (MemoryType.GOAL, {"goal", "want", "plan", "aim", "intend", "hope", "ship"}),
    (MemoryType.PREFERENCE, {"prefer", "like", "dislike", "favorite", "favourite", "love", "hate"}),
    (MemoryType.SKILL, {"can", "able", "skill", "know", "learned", "expert", "proficient"}),
    (MemoryType.PROJECT, {"project", "building", "working", "build", "developing"}),
    (MemoryType.EXPERIENCE, {"yesterday", "happened", "went", "did", "met", "attended", "demo"}),
]


class DeterministicLLMProvider(LLMProvider):
    @property
    def model_name(self) -> str:
        return "deterministic-extractor-v1"

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        return " ".join(prompt.split())

    async def structured_generate(
        self, prompt: str, *, schema: dict[str, str], system: str | None = None
    ) -> dict[str, Any]:
        text = prompt.strip()
        out: dict[str, Any] = {}
        for key in schema:
            if key == "memory_worthy":
                out[key] = self._worthy(text)
            elif key == "candidates":
                out[key] = self._candidates(text)
            elif key == "memory_type":
                out[key] = self._classify(text)
            elif key == "importance":
                out[key] = self._importance(text)
            elif key == "confidence":
                out[key] = self._confidence(text)
            else:
                out[key] = None
        return out

    async def health_check(self) -> bool:
        return True

    # -- deterministic heuristics ------------------------------------------
    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [w.lower() for w in _WORD.findall(text)]

    def _worthy(self, text: str) -> bool:
        return len(text) >= 10 and len(self._tokens(text)) >= 3

    def _candidates(self, text: str) -> list[str]:
        out = []
        for raw in _SENTENCE_SPLIT.split(text):
            sentence = raw.strip()
            if len(sentence) >= 5 and len(self._tokens(sentence)) >= 2:
                out.append(sentence)
        return out

    def _classify(self, text: str) -> str:
        tokens = set(self._tokens(text))
        for memory_type, markers in _TYPE_RULES:
            if tokens & markers:
                return memory_type.value
        return MemoryType.FACT.value

    def _importance(self, text: str) -> float:
        tokens = self._tokens(text)
        emphasis = len(set(tokens) & _EMPHASIS)
        length_factor = min(0.3, len(tokens) / 100.0)
        return round(min(1.0, 0.45 + 0.12 * emphasis + length_factor), 4)

    def _confidence(self, text: str) -> float:
        tokens = set(self._tokens(text))
        hedges = len(tokens & _HEDGES)
        return round(max(0.1, 0.8 - 0.2 * hedges), 4)
