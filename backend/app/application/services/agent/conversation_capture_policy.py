"""ConversationCapturePolicy — lightweight pre-filter for conversational capture.

Decides whether a user's conversation turn is worth handing to the extraction
pipeline. It is deliberately a *pre-filter*, not the final authority: the
extraction engine (worthiness, classification, confidence) and the consolidation
pipeline make the final determination. The policy's job is only to cheaply, and
without an LLM, drop the obvious non-memories (greetings, acknowledgements,
questions, requests, and contentless trivia).

Decision (weighted signals; first-person is one signal among many, not required):

  Hard reject when the turn is:
    * too short (< ``min_tokens``)
    * a greeting / acknowledgement ("hi", "thanks", "ok", "thank you", ...)
    * a question (ends with "?")
    * a request / imperative ("explain ...", "debug ...", "write ...", ...)

  Otherwise capture iff at least ONE positive signal is present:
    first-person | preference | goal/plan | skill | profile (a "name" mention).

Pure, framework-free, deterministic.
"""

from __future__ import annotations

from app.application.services.retrieval.bm25 import tokenize

# --- negative signals (hard rejects) ---------------------------------------
_GREETING_ACK_WORDS = frozenset(
    {
        "hi", "hello", "hey", "yo", "sup", "hiya", "heya", "greetings",
        "thanks", "thank", "thx", "ty", "cheers",
        "ok", "okay", "k", "kk", "cool", "nice", "great", "awesome", "sure",
        "fine", "yes", "yeah", "yep", "yup", "no", "nope", "nah",
        "lol", "haha", "hmm", "bye", "goodbye",
    }
)
_ACK_PHRASES = frozenset(
    {
        "thank you", "got it", "no problem", "sounds good", "will do",
        "makes sense", "good morning", "good evening", "good night", "no worries",
    }
)
_REQUEST_LEADS = frozenset(
    {
        "explain", "describe", "define", "tell", "help", "show", "give", "list",
        "compare", "debug", "fix", "write", "generate", "summarize", "summarise",
        "translate", "calculate", "convert", "find", "search", "recommend",
        "suggest", "create", "make", "build me", "draft",
    }
)

# --- positive signals (any one is enough) ----------------------------------
_FIRST_PERSON = frozenset({"i", "my", "me", "mine", "myself", "im"})
_PREFERENCE = frozenset(
    {"prefer", "prefers", "preferred", "favorite", "favourite", "like", "likes",
     "love", "loves", "enjoy", "enjoys", "hate", "hates", "dislike"}
)
_GOAL_PLAN = frozenset(
    {"goal", "goals", "want", "wanna", "learning", "learn", "studying", "study",
     "planning", "plan", "building", "build", "working", "currently", "aiming",
     "aim", "developing", "develop", "intend", "hope", "startup"}
)
_SKILL = frozenset(
    {"skilled", "skill", "skills", "experienced", "experience", "proficient",
     "expert", "know", "knowledge", "familiar", "capable", "fluent"}
)
_POSITIVE_SETS = (_FIRST_PERSON, _PREFERENCE, _GOAL_PLAN, _SKILL)


class ConversationCapturePolicy:
    def __init__(self, min_tokens: int = 2) -> None:
        self._min_tokens = min_tokens

    def should_capture(self, text: str) -> bool:
        raw = (text or "").strip()
        if not raw:
            return False

        normalized = raw.rstrip("?!. ").lower()
        if normalized in _ACK_PHRASES:
            return False

        tokens = tokenize(raw)
        if len(tokens) < self._min_tokens:
            return False
        if tokens[0] in _GREETING_ACK_WORDS:
            return False
        if raw.endswith("?"):
            return False
        if tokens[0] in _REQUEST_LEADS:
            return False

        token_set = set(tokens)
        if "name" in token_set:  # profile signal ("my name is ...", "name: ...")
            return True
        return any(token_set & signals for signals in _POSITIVE_SETS)
