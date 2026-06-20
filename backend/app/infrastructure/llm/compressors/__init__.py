"""LLM-based context compression (Stage 10 Phase 3).

``LLMContextCompressor`` implements the application's ``ContextCompressor`` port
using an ``LLMProvider`` to summarize a memory set into a budget-fitting context
string. It validates every LLM response and falls back to the deterministic
``HeuristicContextCompressor`` on any failure, so context generation can never
fail because of the LLM. Lives in ``infrastructure`` because it drives an LLM.
"""
