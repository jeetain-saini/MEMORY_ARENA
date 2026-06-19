"""Application layer - use cases (application business rules).

Orchestrates the domain to fulfill user intents. Defines the PORTS
(application/interfaces) it depends on; never references concrete
infrastructure. Depends inward on `domain` only.
Stage 0: structure only - no implementation.
"""