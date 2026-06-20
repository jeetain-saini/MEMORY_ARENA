"""Observability adapters (Stage 13).

Concrete implementations of the observability ports: the real monotonic clock
and the trace recorders (no-op, in-memory, LangSmith). The application layer
depends only on the ports; these adapters are wired at the composition root.
"""
