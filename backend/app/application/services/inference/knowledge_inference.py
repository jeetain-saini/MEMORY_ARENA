"""KnowledgeInferenceLayer — deterministic conversation → structured knowledge.

A *pre-extraction* layer (Phase A). It runs BEFORE the existing LLM extraction
pipeline and transforms a natural conversational turn into a single structured
*knowledge statement* (e.g. "What is Rust?" -> "Interested in Rust"). The raw
question is never stored: the inferred statement is fed into the existing
extraction → consolidation → graph → summary pipeline unchanged.

Design goals:
  * Pure, framework-free, deterministic (no LLM) -> fully unit-testable.
  * Conservative: only emits for *durable knowledge* it recognises; returns
    None for general questions / temporary chat (which then either fall through
    to the existing pipeline unchanged or are dropped by the capture policy).
  * Every result carries confidence, importance, and a reason_for_inference.

This module adds capability; it modifies nothing in the existing pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.value_objects.memory_type import MemoryType

# Canonical names for technologies/topics we recognise (lower-case key -> label).
_TECH: dict[str, str] = {
    "python": "Python", "rust": "Rust", "go": "Go", "golang": "Go", "java": "Java",
    "fastapi": "FastAPI", "langgraph": "LangGraph", "langchain": "LangChain",
    "neo4j": "Neo4j", "postgres": "Postgres", "postgresql": "Postgres",
    "redis": "Redis", "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "react": "React", "nextjs": "Next.js", "next.js": "Next.js",
    "tensorflow": "TensorFlow", "pytorch": "PyTorch", "cuda": "CUDA",
    "rag": "RAG", "sql": "SQL", "typescript": "TypeScript", "javascript": "JavaScript",
}
# Generic infrastructure suffixes: "a Rust API" / "a FastAPI backend" -> Uses <Tech>.
_INFRA_SUFFIX = frozenset({"api", "backend", "service", "server", "microservice", "system", "systems"})


@dataclass(frozen=True)
class InferredKnowledge:
    """A structured, durable knowledge statement inferred from a conversation."""

    statement: str
    memory_type: MemoryType
    confidence: float
    importance: float
    reason: str
    topic: str | None = None
    progression_stage: str | None = None


def _find_tech(text: str) -> str | None:
    """Return the canonical label of the first known technology mentioned."""
    for token in re.findall(r"[a-zA-Z0-9.+#]+", text.lower()):
        if token in _TECH:
            return _TECH[token]
    return None


def _titleize(phrase: str) -> str:
    """Title-case a phrase while preserving known-tech casing (RAG, FastAPI)."""
    words = []
    for w in phrase.split():
        canon = _TECH.get(w.lower())
        words.append(canon if canon else (w.capitalize() if w.islower() else w))
    return " ".join(words)


# Pattern groups, evaluated most-specific first. Each entry: (regex, builder).
def infer(text: str) -> InferredKnowledge | None:
    """Infer one durable knowledge statement from a turn, or None."""
    raw = (text or "").strip()
    if not raw:
        return None
    low = raw.lower().rstrip(" .!?")

    # 1) Experience: multi-year usage -> Experienced with <Tech> (SKILL).
    _years = r"\b(?:\d+\+?|one|two|three|four|five|six|seven|eight|nine|ten|several|many)\s*(?:years?|yrs?)\b"
    if re.search(_years, low) or "for years" in low:
        tech = _find_tech(low)
        if tech:
            return InferredKnowledge(
                f"Experienced with {tech}", MemoryType.SKILL, 0.9, 0.8,
                f"Multi-year experience with {tech} mentioned.",
            )

    # 2) Completed project / internship -> Completed ... (PROJECT / EXPERIENCE).
    m = re.search(r"\b(?:i|i've|i have)\s+(?:finished|completed|shipped|launched)\s+(?:my|the|a|an)?\s*(.+)", low)
    if m:
        obj = m.group(1).strip()
        if "internship" in obj:
            return InferredKnowledge("Completed internship", MemoryType.EXPERIENCE, 0.85, 0.6,
                                     "Reported completing an internship.")
        return InferredKnowledge(f"Completed project: {_titleize(obj)}", MemoryType.PROJECT, 0.85, 0.6,
                                 f"Reported finishing a project ({_titleize(obj)}).")

    # 3) Upcoming internship / job -> EXPERIENCE.
    if "internship" in low and re.search(r"\b(start|starts|starting|begins|next month|upcoming)\b", low):
        return InferredKnowledge("Upcoming internship", MemoryType.EXPERIENCE, 0.8, 0.6,
                                 "Mentioned an upcoming internship.")

    # 4) Career goal: "want to become/be a <role>" -> GOAL.
    #    Capture from the original-case text so roles like "ML Engineer" survive.
    m = re.search(r"\bwant to (?:become|be)\s+(?:an|a)?\s*(.+)", raw, re.IGNORECASE)
    if m:
        role = m.group(1).strip().rstrip(".!?")
        return InferredKnowledge(f"Career goal: {role}", MemoryType.GOAL, 0.85, 0.8,
                                 f"Stated a career aspiration ({role}).")

    # 5) Uses / building with a technology -> Uses <Tech> (SKILL).
    m = re.search(r"\b(?:i|i'm|i am|i've|i have)\s+(?:built|build|building|use|using|develop|developing|deploy|deploying|wrote|writing)\s+(?:a|an|my|the)?\s*(.+)", low)
    if m:
        obj = m.group(1).strip()
        tech = _find_tech(obj)
        last = re.sub(r"[^a-z0-9.+#]", "", obj.split()[-1]) if obj.split() else ""
        if tech and (obj.strip() in {tech.lower(), "the " + tech.lower()} or last in _INFRA_SUFFIX):
            return InferredKnowledge(f"Uses {tech}", MemoryType.SKILL, 0.85, 0.7,
                                     f"Reported building/using {tech}.")
        # A named product (e.g. "RAG chatbot") -> current project.
        return InferredKnowledge(f"Current project: {_titleize(obj)}", MemoryType.PROJECT, 0.8, 0.7,
                                 f"Reported actively building {_titleize(obj)}.")

    # 6) Working on <project> -> current project (PROJECT).
    m = re.search(r"\bworking on\s+(?:a|an|my|the)?\s*(.+)", low)
    if m:
        obj = m.group(1).strip()
        return InferredKnowledge(f"Current project: {_titleize(obj)}", MemoryType.PROJECT, 0.8, 0.7,
                                 f"Reported working on {_titleize(obj)}.")

    # 7) Learning: "teach me X" / "learning X" / "learn X" -> Learning <Tech> (SKILL).
    if re.search(r"\b(teach me|help me learn|learning|learn|studying|study)\b", low):
        tech = _find_tech(low)
        if tech:
            return InferredKnowledge(f"Learning {tech}", MemoryType.SKILL, 0.7, 0.5,
                                     f"Asked to learn or is learning {tech}.")

    # 8) Interest from a question about a known technology -> Interested in <Tech>.
    if (raw.endswith("?") or re.match(r"^\s*(what|explain|describe|tell me about|how does|what's|whats)\b", low)):
        tech = _find_tech(low)
        if tech:
            return InferredKnowledge(f"Interested in {tech}", MemoryType.PREFERENCE, 0.6, 0.4,
                                     f"Asked about {tech} → inferred interest.")
        return None  # general question, no durable knowledge

    # 9) Generic goal: "want to <X>" (non-career) -> GOAL.
    m = re.search(r"\b(?:want to|trying to|focusing on|aiming to)\s+(.+)", low)
    if m:
        goal = _titleize(m.group(1).strip())
        return InferredKnowledge(f"Goal: {goal}", MemoryType.GOAL, 0.75, 0.7,
                                 f"Stated a personal goal ({goal}).")

    return None


class KnowledgeInferenceLayer:
    """Thin object wrapper around :func:`infer` for DI / wiring."""

    def infer(self, text: str) -> InferredKnowledge | None:
        return infer(text)
