"""Ports - abstract repositories & services the use cases depend on.

Use cases say "I need a MemoryRepository" without knowing it is Postgres.
This dependency inversion is the linchpin of swappable infrastructure.
Stage 0: structure only - no implementation.
"""