"""Agent reliability: empty/failed LLM completions never reach the user.

node_generate retries the provider, then falls back to a deterministic answer
built from the retrieved context — so a query always resolves to a non-empty
answer even when the model intermittently returns blank or raises.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.application.dto.agent_dto import AgentConfig
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.infrastructure.llm.graphs.agent_steps import AgentState, node_generate


class _Provider:
    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def model_name(self) -> str:
        return "fake"

    async def generate(self, prompt, *, system=None):  # noqa: ANN001
        self.calls += 1
        out = self._outputs.pop(0) if self._outputs else ""
        if isinstance(out, Exception):
            raise out
        return out

    async def structured_generate(self, *a, **k):  # pragma: no cover
        return {}

    async def health_check(self) -> bool:  # pragma: no cover
        return True


def _state(context_text: str | None = None) -> AgentState:
    s = AgentState(user_id=uuid4(), query="What is my favorite language?", config=AgentConfig())
    if context_text is not None:
        s.context_package = SimpleNamespace(context_text=context_text)
    return s


def _run(provider, state) -> AgentState:
    return asyncio.run(node_generate(state, provider, HeuristicTokenCounter()))


def test_empty_completion_falls_back_to_context() -> None:
    state = _state(context_text="My favorite language is Go")
    out = _run(_Provider(["", "", ""]), state)
    assert out.answer.strip() != ""               # never blank
    assert "Go" in out.answer                       # surfaces the retrieved truth


def test_empty_completion_without_context_still_non_empty() -> None:
    out = _run(_Provider(["", "", ""]), _state(context_text=None))
    assert out.answer.strip() != ""


def test_retry_recovers_after_transient_empty() -> None:
    p = _Provider(["", "Your favorite language is Go."])
    out = _run(p, _state(context_text="My favorite language is Go"))
    assert out.answer == "Your favorite language is Go."  # used the retry, not fallback
    assert p.calls == 2


def test_retry_recovers_after_exception() -> None:
    p = _Provider([RuntimeError("nvidia blipped"), "Recovered answer."])
    out = _run(p, _state(context_text="ctx"))
    assert out.answer == "Recovered answer."
    assert p.calls == 2


def test_first_success_no_extra_calls() -> None:
    p = _Provider(["Immediate answer."])
    out = _run(p, _state(context_text="ctx"))
    assert out.answer == "Immediate answer."
    assert p.calls == 1  # no retry overhead on the happy path
