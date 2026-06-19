"""API layer - HTTP delivery (FastAPI controllers/routers).

Translates HTTP <-> use cases. A delivery mechanism, not the system itself;
the same use cases could be exposed over gRPC or a queue with no core change.
Stage 0: structure only - no implementation.
"""