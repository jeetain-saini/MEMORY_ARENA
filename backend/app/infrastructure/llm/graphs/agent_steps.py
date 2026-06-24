"""Shared agent stages, guardrails, and (de)serialization helpers.

Single source of truth for the query-time agent's behavior. Both
``SequentialAgentRuntime`` and ``LangGraphAgentRuntime`` drive the same node
functions here, so the two never diverge (mirroring ``extraction_steps`` /
``consolidation_steps``).

Stages: retrieve -> expand -> build_context -> generate -> finalize_citations.

Guardrails (enforced in these helpers, so every runtime gets them):
  * max_iterations  — planning-round ceiling (future tool loops)
  * max_tool_calls  — total tool invocations across the run
  * token           — context budget (the builder guarantees it) + answer cap
  * timeout         — applied by the runtime wrapping these helpers

No LangGraph import here; this module is pure orchestration over the existing
services and is itself framework-free. ``ContextPackage`` is the primary artifact
the answer is generated from.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from app.application.dto.agent_dto import (
    FINISH_ERROR,
    FINISH_MAX_ITERATIONS,
    FINISH_MAX_TOOL_CALLS,
    FINISH_TIMEOUT,
    AgentCitation,
    AgentMessage,
    AgentRequest,
    AgentResponse,
    AgentState,
    AgentStepResult,
    AgentStreamEvent,
    AgentTrace,
)
from app.application.dto.observability_dto import (
    ContextTrace,
    GraphExpansionTrace,
    RequestTrace,
    RetrievalTrace,
    SeedExpansion,
    StepTiming,
)
from app.application.interfaces.clock import Clock
from app.application.interfaces.llm_provider import LLMProvider
from app.application.interfaces.token_counter import TokenCounter
from app.application.services.agent.citation_validation import build_citations
from app.application.services.agent.toolset import AgentToolSet
from app.infrastructure.observability.monotonic_clock import MonotonicClock

AGENT_VERSION = "agent-v1"

ANSWER_SYSTEM_PROMPT = (
    "You are MemoryArena's answering agent. You receive the user's question and a "
    "set of retrieved memories about the user.\n"
    "- Use the memories only when they are relevant to answering the question, and "
    "ground user-specific facts in them.\n"
    "- If the memories are not relevant, answer entirely from your own general "
    "knowledge.\n"
    "- When the memories are irrelevant, do NOT mention, summarize, list, "
    "describe, or discuss them; do not explain what memories are available; do not "
    "state what topics the memories contain.\n"
    "- Never invent user-specific facts or claim a memory that is not in the "
    "provided context. Be concise."
)


# --- state init / response assembly ----------------------------------------

def init_state(request: AgentRequest, *, clock: Clock | None = None) -> AgentState:
    state = AgentState(
        user_id=request.user_id,
        query=request.query,
        config=request.config,
        metadata=dict(request.metadata),
        clock=clock or MonotonicClock(),
    )
    state.messages.append(AgentMessage(role="user", content=request.query))
    return state


def to_response(state: AgentState) -> AgentResponse:
    total_duration_ms = round(sum(s.duration_ms for s in state.steps), 3)
    trace = AgentTrace(
        steps=list(state.steps),
        iterations=state.iteration,
        tool_calls=state.tool_calls,
        total_tokens=state.total_tokens,
        finish_reason=state.finish_reason,
        total_duration_ms=total_duration_ms,
    )
    return AgentResponse(
        query=state.query,
        user_id=state.user_id,
        answer=state.answer,
        citations=list(state.citations),
        trace=trace,
        finish_reason=state.finish_reason,
        request_trace=build_request_trace(state),
    )


# --- timing helpers ---------------------------------------------------------

def _now(state: AgentState) -> float:
    return state.clock.now() if state.clock is not None else 0.0


def _elapsed_ms(state: AgentState, start: float) -> float:
    if state.clock is None:
        return 0.0
    return round((state.clock.now() - start) * 1000.0, 3)


# --- guard / termination helpers -------------------------------------------

def _terminate(state: AgentState, reason: str, step_label: str) -> None:
    state.finish_reason = reason
    state.terminated = True
    state.steps.append(AgentStepResult(step=step_label, ok=False, error=reason))


async def _invoke(state: AgentState, tool, step_label: str, *, critical: bool) -> None:
    # max_tool_calls guard (counts every tool invocation across the run).
    if state.tool_calls >= state.config.max_tool_calls:
        _terminate(state, FINISH_MAX_TOOL_CALLS, step_label)
        return
    state.tool_calls += 1
    start = _now(state)
    step = await tool.run(state)  # tools catch their own service errors
    step = replace(step, duration_ms=_elapsed_ms(state, start))
    state.steps.append(step)
    state.total_tokens += step.tokens
    if not step.ok and critical:
        # The context package is the primary artifact: losing it is terminal.
        state.finish_reason = FINISH_ERROR
        state.terminated = True


def _truncate(text: str, budget_tokens: int, counter: TokenCounter) -> str:
    if counter.count(text) <= budget_tokens:
        return text
    max_chars = max(1, budget_tokens * 4)  # ~4 chars/token (token guard)
    return text[:max_chars].rstrip()


def build_answer_prompt(state: AgentState) -> str:
    package = state.context_package
    context_text = package.context_text if package is not None else ""
    parts = [
        f"User question: {state.query}",
        "",
        "Context (assembled, deduplicated, compressed memories):",
        context_text or "(no context available)",
    ]
    expanded = state.expanded
    if expanded is not None and expanded.graph_count:
        related = [m.content for m in expanded.results if m.provenance == "graph"]
        if related:
            parts.append("")
            parts.append("Related memories (via knowledge graph):")
            parts.extend(f"- {c}" for c in related[:10])
    parts.append("")
    parts.append(
        "Answer the question. Reference the memories above only when they are "
        "directly relevant to the question; if they do not help, answer normally "
        "from general knowledge and do not refer to, enumerate, or summarize the "
        "memories. Do not invent memories that are not listed above."
    )
    return "\n".join(parts)


def _finalize_citations(state: AgentState) -> None:
    package = state.context_package
    if package is None:
        state.citations = []
        return
    known = set(state.provenance)
    state.citations = build_citations(
        package.memories,
        state.provenance,
        known,
        state.config.max_citations,
        answer=state.answer,
        grounding_threshold=state.config.citation_grounding_threshold,
    )


# --- request-scoped trace assembly (Stage 13 observability) ----------------

def build_request_trace(state: AgentState) -> RequestTrace:
    """Assemble the request-scoped trace from the agent state.

    Pure projection over data the pipeline already produced (retrieval, graph
    expansion, context package, per-stage timings). Re-runs nothing.
    """
    timings = [StepTiming(step=s.step, duration_ms=s.duration_ms, ok=s.ok) for s in state.steps]
    total_duration_ms = round(sum(s.duration_ms for s in state.steps), 3)

    retrieval_trace: RetrievalTrace | None = None
    if state.retrieved is not None:
        retrieval_trace = RetrievalTrace(
            query=state.query,
            candidate_count=state.retrieved.count,
            returned_count=len(state.retrieved.results),
            top_scores=[round(r.final_score, 6) for r in state.retrieved.results[:20]],
            duration_ms=_step_duration(state, "retrieve"),
        )

    graph_trace: GraphExpansionTrace | None = None
    if state.expanded is not None:
        graph_results = [m for m in state.expanded.results if m.provenance == "graph"]
        seed_counts: dict[object, int] = {}
        for m in graph_results:
            if m.source_memory_id is not None:
                seed_counts[m.source_memory_id] = seed_counts.get(m.source_memory_id, 0) + 1
        graph_trace = GraphExpansionTrace(
            enabled=state.config.expand_graph,
            hybrid_count=state.expanded.hybrid_count,
            graph_count=state.expanded.graph_count,
            influence_scores=[round(m.score, 6) for m in graph_results[:20]],
            seeds=[SeedExpansion(seed_memory_id=sid, neighbors_admitted=n) for sid, n in seed_counts.items()],
            duration_ms=_step_duration(state, "expand"),
        )

    context_trace: ContextTrace | None = None
    package = state.context_package
    if package is not None:
        utilization = round(package.total_tokens / package.max_tokens, 6) if package.max_tokens else 0.0
        context_trace = ContextTrace(
            memory_count=len(package.memories),
            total_tokens=package.total_tokens,
            max_tokens=package.max_tokens,
            budget_utilization=utilization,
            duration_ms=_step_duration(state, "build_context"),
        )

    return RequestTrace(
        query=state.query,
        user_id=state.user_id,
        finish_reason=state.finish_reason,
        total_duration_ms=total_duration_ms,
        timings=timings,
        retrieval=retrieval_trace,
        graph=graph_trace,
        context=context_trace,
        iterations=state.iteration,
        tool_calls=state.tool_calls,
        total_tokens=state.total_tokens,
    )


def _step_duration(state: AgentState, label: str) -> float:
    return round(sum(s.duration_ms for s in state.steps if s.step == label), 3)


# --- node functions (shared by both runtimes) ------------------------------

async def node_retrieve(state: AgentState, toolset: AgentToolSet) -> AgentState:
    if state.terminated:
        return state
    state.iteration += 1
    if state.iteration > state.config.max_iterations:
        _terminate(state, FINISH_MAX_ITERATIONS, "retrieve")
        return state
    await _invoke(state, toolset.search, "retrieve", critical=False)
    return state


async def node_expand(state: AgentState, toolset: AgentToolSet) -> AgentState:
    if state.terminated or not state.config.expand_graph:
        return state
    await _invoke(state, toolset.expansion, "expand", critical=False)
    return state


async def node_build(state: AgentState, toolset: AgentToolSet) -> AgentState:
    if state.terminated:
        return state
    await _invoke(state, toolset.context, "build_context", critical=True)
    return state


# The configured LLM (e.g. some NVIDIA NIM models) intermittently returns an
# empty completion. Retry a few times, then deterministically fall back to the
# retrieved context, so a user query never resolves to a blank answer.
_GENERATE_ATTEMPTS = 3


def _fallback_answer(state: AgentState) -> str:
    """A non-empty answer synthesized from retrieved memories when the LLM fails.

    The user never sees a blank response: if memories were retrieved, surface
    them; otherwise say so plainly.
    """
    package = state.context_package
    context_text = (package.context_text if package is not None else "").strip()
    if context_text:
        return f"Based on your memories: {context_text}"
    return "I couldn't find anything in your memories to answer that."


async def node_generate(
    state: AgentState, provider: LLMProvider, counter: TokenCounter
) -> AgentState:
    if state.terminated:
        return state
    prompt = build_answer_prompt(state)
    start = _now(state)

    raw = ""
    last_error: str | None = None
    for _attempt in range(_GENERATE_ATTEMPTS):
        try:
            candidate = (await provider.generate(prompt, system=ANSWER_SYSTEM_PROMPT) or "").strip()
        except Exception as exc:  # noqa: BLE001 — retry, then fall back
            last_error = str(exc)
            candidate = ""
        if candidate:  # answer validation: only accept non-empty completions
            raw = candidate
            break

    used_fallback = not raw
    if used_fallback:
        raw = _fallback_answer(state)  # guarantees a non-empty answer

    answer = _truncate(raw, state.config.answer_max_tokens, counter)
    state.answer = answer
    tokens = counter.count(answer)
    state.total_tokens += tokens
    state.messages.append(AgentMessage(role="assistant", content=answer))
    state.steps.append(
        AgentStepResult(
            step="generate",
            ok=True,
            summary=(
                f"generated answer (fallback after empty/failed generation: {last_error})"
                if used_fallback
                else "generated answer"
            ),
            tokens=tokens,
            duration_ms=_elapsed_ms(state, start),
        )
    )
    return state


# --- drivers ----------------------------------------------------------------

async def execute(
    state: AgentState, toolset: AgentToolSet, provider: LLMProvider, counter: TokenCounter
) -> AgentState:
    """Run the full linear flow to completion (timeout applied by the caller)."""
    await node_retrieve(state, toolset)
    await node_expand(state, toolset)
    await node_build(state, toolset)
    await node_generate(state, provider, counter)
    _finalize_citations(state)
    return state


async def stream_events(
    state: AgentState, toolset: AgentToolSet, provider: LLMProvider, counter: TokenCounter
):
    """Async generator of per-stage events (timeout applied by the caller)."""
    stages = [
        ("retrieve", lambda: node_retrieve(state, toolset)),
        ("expand", lambda: node_expand(state, toolset)),
        ("build_context", lambda: node_build(state, toolset)),
        ("generate", lambda: node_generate(state, provider, counter)),
    ]
    for _label, run in stages:
        before = len(state.steps)
        await run()
        for step in state.steps[before:]:
            yield AgentStreamEvent(event="step", data=step_payload(step))
        if state.terminated:
            break

    if state.terminated and state.finish_reason in (FINISH_ERROR, FINISH_TIMEOUT):
        yield AgentStreamEvent(event="error", data={"finish_reason": state.finish_reason})
        return

    _finalize_citations(state)
    yield AgentStreamEvent(event="answer", data={"answer": state.answer})
    yield AgentStreamEvent(event="citations", data={"citations": citations_payload(state.citations)})


async def stream_with_timeout(
    state: AgentState,
    toolset: AgentToolSet,
    provider: LLMProvider,
    counter: TokenCounter,
    timeout: float,
):
    """Wrap ``stream_events`` with an overall timeout and a terminal ``done``.

    Shared by both runtimes. Always yields a final ``done`` event (and an
    ``error`` event before it on timeout). On client disconnect the
    ``CancelledError`` propagates after the underlying generator is closed.
    """
    gen = stream_events(state, toolset, provider, counter)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                state.finish_reason = FINISH_TIMEOUT
                state.terminated = True
                yield AgentStreamEvent(event="error", data={"finish_reason": FINISH_TIMEOUT})
                break
            try:
                event = await asyncio.wait_for(gen.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                state.finish_reason = FINISH_TIMEOUT
                state.terminated = True
                yield AgentStreamEvent(event="error", data={"finish_reason": FINISH_TIMEOUT})
                break
            yield event
    finally:
        await gen.aclose()
    yield AgentStreamEvent(event="done", data=done_payload(state))


# --- serialization helpers (for SSE + use-case/API mapping) ----------------

def step_payload(step: AgentStepResult) -> dict:
    return {
        "step": step.step,
        "ok": step.ok,
        "summary": step.summary,
        "error": step.error,
        "tool": step.tool_call.tool_name if step.tool_call else None,
        "duration_ms": step.duration_ms,
    }


def citations_payload(citations: list[AgentCitation]) -> list[dict]:
    return [
        {
            "memory_id": str(c.memory_id),
            "content": c.content,
            "memory_type": c.memory_type.value,
            "provenance": c.provenance,
            "score": c.score,
        }
        for c in citations
    ]


def done_payload(state: AgentState) -> dict:
    return {
        "finish_reason": state.finish_reason,
        "iterations": state.iteration,
        "tool_calls": state.tool_calls,
        "total_duration_ms": round(sum(s.duration_ms for s in state.steps), 3),
        "answer": state.answer,
        "citations": citations_payload(state.citations),
    }
