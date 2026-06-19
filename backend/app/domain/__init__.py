"""Domain layer - enterprise business rules (the stable center).

Pure Python objects encoding *what a memory is* and *the rules it obeys*:
entities, value objects, domain events, domain exceptions.

INVARIANT: imports NOTHING from outer layers and NO third-party frameworks
(no FastAPI, SQLAlchemy, Neo4j, Redis, pydantic). Testable with zero I/O.
Stage 0: structure only - no implementation.
"""