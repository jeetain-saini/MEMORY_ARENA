# MemoryArena — Architecture

**Status:** Stages 0–9 complete (Knowledge Graph) · **Audience:** Engineers, architects, reviewers
**Scope:** This document defines the architecture, the reasoning behind every structural decision, and the rules that keep the system maintainable as it grows toward millions of users. It describes *intent*; Stage 0 contains no business logic.

---

## 1. What MemoryArena Is

MemoryArena is a **memory backend for AI agents**. Agents and applications send it raw signal — conversations, events, documents — and it returns **structured, retrievable memory**:

- **Semantic memory** — facts and knowledge ("the user prefers async meetings"), stored as text + vector embeddings in **pgvector**.
- **Episodic memory** — time-stamped events ("on June 3 the user cancelled plan X"), stored relationally in **PostgreSQL**.
- **Relational/graph memory** — entities and how they connect ("Alice → works_at → Acme → competitor_of → Globex"), stored in **Neo4j**.

The hard problems are *extraction* (turning messy input into clean memory), *consolidation* (merging, deduplicating, and decaying memory over time), and *retrieval* (returning the right memory fast). Extraction and consolidation are modeled as **LangGraph** stateful workflows; retrieval blends vector similarity, graph traversal, and Redis-cached hot paths.

---

## 2. Architectural Style: Clean Architecture

We adopt **Clean Architecture** (a.k.a. Hexagonal / Ports & Adapters). The system is organized as concentric layers, and **all source-code dependencies point inward**.

```
            ┌─────────────────────────────────────────────┐
            │                  api  (FastAPI)              │  ← Frameworks & Drivers
            │     ┌─────────────────────────────────┐      │
            │     │   infrastructure / repositories  │      │  ← Interface Adapters
            │     │   ┌─────────────────────────┐    │      │
            │     │   │      application        │    │      │  ← Use Cases
            │     │   │   ┌─────────────────┐   │    │      │
            │     │   │   │     domain      │   │    │      │  ← Enterprise Rules
            │     │   │   └─────────────────┘   │    │      │
            │     │   └─────────────────────────┘    │      │
            │     └─────────────────────────────────┘      │
            └─────────────────────────────────────────────┘

        Dependencies point INWARD only.  Domain knows nothing of the rest.
```

### The Dependency Rule (the one rule everything else serves)

> Nothing in an inner circle may know anything about an outer circle.

Concretely:

- `domain/` imports **nothing** from the project — not FastAPI, not SQLAlchemy, not Neo4j, not pydantic schemas.
- `application/` imports `domain/`, and depends on **interfaces (ports)** it defines — never on concrete databases.
- `infrastructure/` and `repositories/` implement those ports using real technology (SQLAlchemy, the Neo4j driver, Redis).
- `api/` wires everything together and translates HTTP ⇄ use cases.

**Why this matters at scale:** the expensive, slow-to-change asset is *business logic*. Frameworks, databases, and LLM providers are commodities we will swap (Postgres today, a sharded variant tomorrow; OpenAI embeddings today, a local model tomorrow). By keeping business rules ignorant of those choices, we can replace any outer layer without touching the core — and we can unit-test the core with **zero** infrastructure spun up.

### Dependency Inversion in practice

The application layer declares an interface it *needs*; the infrastructure layer *provides* an implementation. The api layer injects the concrete one at runtime (FastAPI `Depends`).

```
application/interfaces/memory_repository.py   (abstract port — "I need a place to save memories")
        ▲ implemented by
repositories/memory_repository.py             (adapter — SQLAlchemy + pgvector)
        ▲ injected by
api/v1/dependencies/                          (composition root — wires concrete → abstract)
```

This is why `repositories/` and `schemas/` are **top-level** backend concerns rather than buried: they are the seams where the swappable outside world meets the stable inside.

---

## 3. Monorepo Layout & Why Each Folder Exists

```
memory_project/
├── backend/          # FastAPI service (Clean Architecture)
├── frontend/         # Next.js 15 dashboard & playground
├── infrastructure/   # Dockerfiles, container init, k8s, ops scripts
├── docs/             # This document, ADRs, diagrams
├── tests/            # System-level tests that span services
├── .github/          # CI/CD workflows
├── docker-compose.yml
├── .env.example
└── README.md
```

**Why a monorepo?** The API contract, the client that consumes it, the schema that backs it, and the infra that runs it change *together*. One reviewable PR can move a domain concept end-to-end. It also gives us one CI pipeline, one dependency graph, and atomic cross-cutting refactors — invaluable while the system is still finding its shape.

### 3.1 `backend/` — the FastAPI service

```
backend/
├── app/
│   ├── api/             # HTTP delivery layer (controllers / routers)
│   │   └── v1/
│   │       ├── routes/        # Endpoint definitions, grouped by resource
│   │       ├── dependencies/  # FastAPI Depends — the composition root / DI wiring
│   │       └── middleware/    # Cross-cutting HTTP concerns (auth, request-id, timing)
│   ├── core/            # Framework-agnostic cross-cutting: config, logging, security
│   ├── domain/          # ★ Enterprise business rules — the stable center
│   │   ├── entities/         # Core objects: Memory, Entity, Agent, Tenant
│   │   ├── value_objects/    # Immutable typed values: Embedding, MemoryType, Score
│   │   ├── events/           # Domain events: MemoryCreated, MemoryConsolidated
│   │   └── exceptions/       # Domain-specific errors, independent of HTTP
│   ├── application/     # ★ Use cases — orchestration of domain to fulfill goals
│   │   ├── use_cases/        # One class per user intent (IngestMemory, RetrieveMemory)
│   │   ├── interfaces/       # PORTS — abstract repos & services the use cases depend on
│   │   └── dto/              # Internal data-transfer objects between layers
│   ├── infrastructure/  # Frameworks & drivers — concrete I/O
│   │   ├── database/         # SQLAlchemy engine, session, ORM models (Postgres)
│   │   │   └── models/       # ORM table mappings (NOT domain entities)
│   │   ├── vector/           # pgvector access: embedding storage & similarity search
│   │   ├── cache/            # Redis client & cache abstractions
│   │   ├── graph/            # Neo4j driver & Cypher gateways
│   │   └── llm/              # LangChain/LangGraph integration
│   │       ├── graphs/       # LangGraph stateful workflows (extraction, consolidation)
│   │       └── chains/       # LangChain prompt chains & runnables
│   ├── services/        # Application/domain services — logic spanning >1 entity
│   ├── repositories/    # Concrete implementations of application/interfaces ports
│   └── schemas/         # Pydantic request/response models — the API's public contract
├── alembic/             # Database migrations (versioned schema history)
│   └── versions/
├── tests/               # Backend tests, mirrored to the layer they cover
│   ├── unit/                 # Domain & use cases, no I/O
│   ├── integration/          # Repositories & infra against real containers
│   └── e2e/                  # Full API request → response
├── pyproject.toml       # Dependencies, tooling, build config
├── alembic.ini          # Migration tool config
└── Dockerfile           # (lives under infrastructure/docker/backend in Stage 0)
```

**Folder-by-folder rationale:**

| Folder | Exists because… |
| --- | --- |
| `api/` | HTTP is *a* delivery mechanism, not *the* system. Isolating it means the same use cases could later be exposed over gRPC or a queue consumer with no change to business logic. |
| `api/v1/` | Versioning the API from day one lets us evolve the contract (v2) without breaking existing clients — non-negotiable for a service many agents depend on. |
| `api/v1/dependencies/` | This is the **composition root**: the single place where abstract ports are bound to concrete adapters. Centralizing wiring keeps the dependency rule enforceable. |
| `core/` | Configuration, structured logging, and security primitives are needed everywhere but belong to no single layer. Keeping them framework-agnostic prevents them from leaking framework details inward. |
| `domain/` | The crown jewels. Pure Python objects encoding *what a memory is* and *the rules it obeys*, with no awareness of databases or HTTP. This is what survives every technology migration. |
| `domain/value_objects/` | Concepts like an `Embedding` or a similarity `Score` are values, not entities — immutable and compared by value. Modeling them explicitly removes primitive-obsession bugs. |
| `domain/events/` | Domain events make consolidation, auditing, and future event-driven scaling (outbox → queue) possible without coupling producers to consumers. |
| `application/use_cases/` | Each use case is one unit of business intent. One class, one reason to change — trivially testable and the natural place to enforce transaction boundaries. |
| `application/interfaces/` | The **ports**. Use cases say "I need a `MemoryRepository`" without knowing it's Postgres. This inverts the dependency and is the linchpin of swappable infrastructure. |
| `infrastructure/` | All the messy, fast-changing outside world (drivers, SDKs, network I/O) lives here, behind the ports. It depends inward; nothing inward depends on it. |
| `infrastructure/database/models/` | ORM models are a *persistence detail* and are deliberately separate from `domain/entities/`. Repositories translate between them so the database schema can change without reshaping the domain. |
| `infrastructure/llm/graphs/` | LangGraph workflows are stateful, multi-step, and retry-prone — they get their own home so extraction/consolidation pipelines are first-class and independently testable. |
| `services/` | Some logic legitimately spans multiple entities (e.g., consolidating a memory cluster). Domain/application services hold that orchestration without bloating any single entity. |
| `repositories/` | Concrete adapters implementing the ports. The seam between stable core and swappable storage. |
| `schemas/` | Pydantic models are the *public wire contract*. Keeping them separate from domain entities lets the external API and internal model evolve independently — and prevents accidentally exposing internal fields. |
| `alembic/` | Schema must evolve safely in production with reversible, reviewable, ordered migrations. Never edit a live schema by hand. |

> **Key distinction — three "models," on purpose:** `domain/entities` (business truth) ≠ `infrastructure/database/models` (DB rows) ≠ `schemas` (API wire format). The duplication is intentional decoupling: each can change for its own reasons. Repositories and use cases do the translation.

### 3.2 `frontend/` — Next.js 15 dashboard

```
frontend/
├── src/
│   ├── app/          # Next.js App Router — file-based routes, layouts, server components
│   ├── components/   # Reusable React components
│   │   ├── ui/            # shadcn/ui primitives (generated)
│   │   └── shared/        # Composed, app-specific components
│   ├── hooks/        # Custom React hooks (stateful client logic, data fetching)
│   ├── services/     # API client layer — typed calls to the backend
│   ├── types/        # TypeScript types, mirroring the backend's API contract
│   ├── lib/          # Framework-agnostic utilities & client configuration
│   └── styles/       # Global Tailwind layers & design tokens
├── public/           # Static assets served as-is
├── package.json
├── tsconfig.json
└── tailwind.config.ts
```

| Folder | Exists because… |
| --- | --- |
| `app/` | The Next.js 15 App Router is the routing + rendering boundary (server/client components, streaming, layouts). It is the frontend's "delivery layer." |
| `components/ui/` | shadcn/ui components are copied into the repo (not a black-box dependency), so they live here and are ours to restyle. |
| `components/shared/` | Keeping app-specific composed components apart from primitives mirrors the same "stable primitives vs. evolving composition" split we use on the backend. |
| `hooks/` | Encapsulating client state and data-fetching in hooks keeps components declarative and logic reusable. |
| `services/` | A single typed API client layer means the rest of the app never hand-rolls `fetch` calls — the backend contract is touched in exactly one place. |
| `types/` | Mirroring backend schemas as TS types gives end-to-end type safety; a contract change surfaces as a compile error, not a runtime surprise. |
| `lib/` | Pure helpers and config (date formatting, env access) with no React dependency, reusable on server or client. |

### 3.3 `infrastructure/`

```
infrastructure/
├── docker/           # Per-service Dockerfiles & container init scripts
│   ├── backend/      ├── frontend/    ├── postgres/   ├── neo4j/   └── redis/
├── k8s/              # Kubernetes manifests for production orchestration (future)
├── monitoring/       # Observability config (metrics, dashboards, alerts)
└── scripts/          # Operational & developer scripts (seeding, backups)
```

Infrastructure-as-config lives beside the code it runs, version-locked with it. Separating it from application code keeps deployment concerns out of the business layers and lets ops evolve independently. `k8s/` and `monitoring/` are placeholders now because designing for millions of users means leaving the door open for orchestration and observability from the start.

### 3.4 `docs/`, `tests/`, `.github/`

| Folder | Exists because… |
| --- | --- |
| `docs/` | Architecture must be written down to stay shared. `docs/adr/` records *why* decisions were made (Architecture Decision Records); `docs/diagrams/` holds visual models. |
| `tests/` (root) | **System-level** tests that span services live here — `e2e/` (full stack), `contract/` (frontend↔backend contract), `load/` (performance at scale). This is distinct from `backend/tests/`, which tests the backend in isolation. |
| `.github/workflows/` | CI/CD as code: lint, type-check, test, build, and deploy gates run on every PR. Quality is enforced by the pipeline, not by hope. |

---

## 4. Request & Data Flow (intended)

**Ingestion (write path):**
```
Client → api/v1/routes → schema validation → use_case (IngestMemory)
      → LangGraph extraction workflow (infrastructure/llm/graphs)
      → repositories: write rows (Postgres) + embeddings (pgvector) + nodes/edges (Neo4j)
      → emit MemoryCreated domain event
```

**Retrieval (read path):**
```
Client → api/v1/routes → use_case (RetrieveMemory)
      → check Redis cache (infrastructure/cache)
      → on miss: pgvector similarity search + Neo4j graph expansion
      → rank/merge in a domain service → cache result → return schema
```

The api and infrastructure layers are interchangeable adapters; the use case in the middle is the same regardless of who calls it or where the data lives.

---

## 5. Designing for Millions of Users

Architecture choices made now so scale is an evolution, not a rewrite:

- **Stateless backend.** No session state in the app process → horizontal scaling behind a load balancer is trivial. State lives in Postgres/Neo4j/Redis.
- **Async-first.** FastAPI + async SQLAlchemy + async drivers maximize throughput per instance under I/O-bound LLM and DB workloads.
- **Read/write separation at the seam.** Repositories hide storage, so read replicas, sharding, or a CQRS split can be introduced behind the same ports without touching use cases.
- **Cache-aside with Redis.** Hot memory retrievals and rate-limit counters are offloaded from the primary stores.
- **Vector + graph specialization.** pgvector for similarity, Neo4j for multi-hop relationships — each store does what it is best at instead of forcing one database to do everything.
- **Workflow isolation.** LangGraph pipelines are retry-safe and can be moved to background workers/queues (via the `events/` + `cache/` queue seam) when ingestion volume grows.
- **API versioning from day one.** `api/v1` lets the contract evolve without breaking the fleet of agents depending on it.
- **Multi-tenancy as a first-class domain concept.** A `Tenant` entity and tenant-scoped queries are designed in from the start, never retrofitted.

---

## 6. Architectural Invariants (enforced going forward)

1. **The dependency rule is absolute** — inner layers never import outer layers. CI will lint import boundaries.
2. **The domain layer has zero third-party framework imports.**
3. **Use cases depend on interfaces, never on concrete infrastructure.**
4. **Three model types stay separate:** domain entities, ORM models, API schemas.
5. **All schema changes go through Alembic migrations.**
6. **Every significant decision gets an ADR** in `docs/adr/`.

---

*Stage 0 establishes the skeleton these invariants protect.*

---

## 7. Stage 1 — Backend Foundation (Bootstrap & Infrastructure)

Stage 1 makes the backend a running, observable, production-ready service — **without any memory logic, LangGraph, embeddings, or repositories**. It delivers the application bootstrap, configuration, structured logging, datastore connectivity, health monitoring, dependency injection, error handling, and container/dev tooling.

### 7.1 New files

```
backend/app/
├── main.py                                  # App factory + startup/shutdown lifecycle
├── core/
│   ├── config.py                            # Pydantic Settings (typed, validated)
│   ├── logging.py                           # JSON logging + correlation-id middleware
│   └── exceptions.py                        # AppException + global exception handlers
├── schemas/
│   └── responses.py                         # Standardized APIResponse / ErrorResponse
├── infrastructure/
│   ├── database/postgres.py                 # PostgresManager (async SQLAlchemy engine)
│   ├── cache/redis.py                       # RedisManager (async client + pool)
│   └── graph/neo4j.py                       # Neo4jManager (async driver)
└── api/v1/
    ├── router.py                            # Aggregate v1 router
    ├── routes/health.py                     # GET /health, GET /version
    └── dependencies/providers.py            # DI providers (settings, db, redis, neo4j)

backend/tests/unit/test_config.py            # Settings validation tests
```

Updated: `pyproject.toml` (Ruff/Black/isort/mypy), `infrastructure/docker/backend/Dockerfile` (entrypoint + HEALTHCHECK), `docker-compose.yml` (backend service enabled), `.env.example` (canonical variable names).

### 7.2 Configuration management

A single `Settings` object (Pydantic Settings) is the **only** way runtime values enter the system. It is loaded once and cached via `get_settings()` (an `lru_cache`), so one immutable, validated instance is shared process-wide. Validation runs at boot — a missing `POSTGRES_URL`, a too-short `JWT_SECRET`, or a leftover `change-me` secret aborts startup rather than failing mid-request. Field names map case-insensitively to env vars (`postgres_url` ← `POSTGRES_URL`).

### 7.3 Structured logging & correlation IDs

`configure_logging()` installs a `JsonFormatter` on the root logger and routes uvicorn's loggers through it, so **every** line is a single JSON object. `RequestContextLogMiddleware` mints a correlation ID per request (honoring an inbound `X-Request-ID`), stores it in a `ContextVar`, logs `request.start` / `request.finish` with millisecond timing, and echoes the ID in the response header. Because the ID lives in a `ContextVar`, *any* log emitted while serving the request is auto-stamped — no manual threading.

### 7.4 Infrastructure architecture — connection managers as singletons

Each datastore gets a manager class (`PostgresManager`, `RedisManager`, `Neo4jManager`) instantiated **once** as a module-level singleton. The rationale: each underlying client already owns a connection *pool*, so the expensive, shareable object is the engine/client/driver itself. Each manager exposes the same lifecycle contract:

| Method | Responsibility |
| --- | --- |
| `connect(settings)` | Idempotently build the pooled client; Neo4j additionally verifies connectivity (fail fast). |
| `disconnect()` | Gracefully dispose the pool. |
| `health_check()` | Cheap liveness probe (`SELECT 1` / `PING` / `RETURN 1`) that **never raises** — it returns `False` so the health endpoint stays up even when a dependency is down. |

```
        ┌──────────────────────── FastAPI app ────────────────────────┐
        │  api/v1/dependencies/providers.py   (composition root, read) │
        │     get_db_session ─┐   get_redis ─┐   get_neo4j ─┐          │
        └─────────────────────┼──────────────┼─────────────┼──────────┘
                              ▼              ▼             ▼
                     PostgresManager   RedisManager   Neo4jManager   (singletons)
                              │              │             │
                         async pool     async pool     driver pool
                              ▼              ▼             ▼
                        PostgreSQL        Redis          Neo4j
```

### 7.5 Dependency injection flow

The composition root has two halves. **Write side** (`main.py` lifespan): on startup the singletons are `connect`-ed; on shutdown they are `disconnect`-ed in reverse order. **Read side** (`providers.py`): thin `Depends(...)` functions hand the live client (or a request-scoped DB session) to route handlers. Handlers ask for *what they need*, never construct it, and can be tested by overriding the provider — preserving the dependency rule end-to-end.

### 7.6 Health monitoring

`GET /api/v1/health` probes all three datastores **concurrently** (`asyncio.gather`) and returns `{ "status", "postgres", "redis", "neo4j" }` — HTTP 200 when all are `up`, HTTP 503 when any is `down`, so orchestrators (Docker/K8s) can gate traffic on readiness. `GET /api/v1/version` returns service name, version, and environment.

### 7.7 Error handling

`register_exception_handlers()` installs handlers for `AppException` (deliberate errors carrying an HTTP status + stable code), `RequestValidationError` (422 with field details), `StarletteHTTPException`, and a catch-all `Exception` that logs the full trace server-side but returns a generic message — internals never leak. Every error is emitted in the standardized `ErrorResponse` envelope, stamped with the correlation ID.

### 7.8 Startup sequence

```
uvicorn app.main:app
        │
        ▼
create_app()
   1. get_settings()              ── load & validate env (fail fast)
   2. configure_logging(level)    ── install JSON formatter
   3. FastAPI(lifespan=...)       ── docs gated by environment
   4. add CORS + RequestContext middleware
   5. register_exception_handlers
   6. include_router(api_router, prefix="/api/v1")
        │
        ▼
lifespan startup  (on first request / server boot)
   7. postgres_manager.connect(settings)
   8. redis_manager.connect(settings)
   9. neo4j_manager.connect(settings)   ── verify_connectivity()
        │
        ▼
   ── SERVING ──  (GET /api/v1/health reports up/up/up)
        │
        ▼
lifespan shutdown (reverse order)
   10. neo4j_manager.disconnect()
   11. redis_manager.disconnect()
   12. postgres_manager.disconnect()
```

*Stage 2 fills the domain layer.*

---

## 8. Stage 2 — Core Domain Model (Self-Evolving Memory)

Stage 2 implements the **domain language** of MemoryArena: pure-Python entities, value objects, events, exceptions, and the application contracts (DTOs, use-case interfaces, repository ports) that surround them. It contains **no infrastructure, no databases, no APIs, no LangGraph** — the domain layer imports only the standard library and itself.

### 8.1 New files

```
backend/app/
├── domain/
│   ├── value_objects/
│   │   ├── memory_type.py          # MemoryType enum (FACT, GOAL, PREFERENCE, SKILL, PROJECT, EXPERIENCE)
│   │   ├── memory_status.py        # MemoryStatus enum + legal transition table
│   │   └── relation_type.py        # RelationType enum (RELATED_TO, DEPENDS_ON, ...)
│   ├── entities/
│   │   ├── memory.py               # Memory aggregate root (state transitions + events)
│   │   ├── memory_score.py         # MemoryScore value object (weighted total)
│   │   ├── memory_relation.py      # MemoryRelation edge entity
│   │   └── memory_version.py       # MemoryVersion immutable snapshot
│   ├── events/
│   │   └── memory_events.py        # MemoryCreated/Updated/Archived/Deleted/Promoted
│   └── exceptions/
│       └── errors.py               # DomainError hierarchy
├── application/
│   ├── dto/memory_dto.py           # Create/Update/Search request + response DTOs
│   ├── use_cases/memory_use_cases.py   # Create/Update/Delete/Search use-case interfaces
│   └── interfaces/repositories.py  # Memory / Relation / Version repository PORTS
└── tests/unit/
    ├── test_memory_score.py        # score math + reinforcement + promotion threshold
    ├── test_memory_entity.py       # transitions, events, validation
    ├── test_memory_relation.py     # edge creation + invariants
    └── test_memory_version.py      # snapshot + rollback
```

### 8.2 Domain model diagram

```
                         ┌──────────────────────────────────────────┐
                         │                 Memory                    │  «aggregate root»
                         │  id · user_id · content                   │
                         │  memory_type : MemoryType  ───────────────┼──▶ «enum» MemoryType
                         │  status      : MemoryStatus ──────────────┼──▶ «enum» MemoryStatus
                         │  score       : MemoryScore                │      (owns transition table)
                         │  version · is_promoted                    │
                         │  created_at · updated_at · metadata       │
                         │  _events : [DomainEvent]                  │
                         └───────┬───────────────┬──────────────┬────┘
                  composes 1     │               │ records *    │ snapshots *
                                 ▼               ▼              ▼
                     ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐
                     │  MemoryScore   │  │ DomainEvent  │  │  MemoryVersion  │ «frozen»
                     │ «frozen VO»    │  │  (frozen)    │  │ memory_id       │
                     │ importance     │  ├──────────────┤  │ version_number  │
                     │ utility        │  │ MemoryCreated│  │ content/type    │
                     │ frequency      │  │ MemoryUpdated│  │ status/metadata │
                     │ recency        │  │ MemoryArchiv.│  │ reason          │
                     │ confidence     │  │ MemoryDeleted│  └─────────────────┘
                     │ +total_score() │  │ MemoryPromot.│
                     └────────────────┘  └──────────────┘

         ┌───────────────────────────────────────────────────────────────┐
         │                       MemoryRelation                           │
         │  source_memory_id ──(relation_type: RelationType)──▶ target_id  │
         │  weight ∈ [0,1] · metadata                                      │
         └───────────────────────────────────────────────────────────────┘

   total_score = 0.30·importance + 0.25·utility + 0.20·frequency
               + 0.15·recency   + 0.10·confidence          (weights Σ = 1.0 ⇒ normalized)
```

### 8.3 Memory lifecycle

```
   Created      Memory.create()           → MemoryCreated      status=ACTIVE, v1
      │
      ▼
   Scored       MemoryScore.calculate_total_score()            (computed, not a state)
      │
      ▼
   Linked       MemoryRelation.create(... RELATED_TO/DEPENDS_ON/DERIVED_FROM ...)
      │
      ▼
   Reinforced   Memory.reinforce()        → score.reinforced() (frequency↑, recency→1.0)
      │
      ▼
   Promoted     Memory.promote()          → MemoryPromoted     is_promoted=True
      │                                     (requires ACTIVE + score ≥ threshold 0.65)
      ▼
   Archived     Memory.archive()          → MemoryArchived     ACTIVE → ARCHIVED
      │                                     (ARCHIVED → ACTIVE via restore())
      ▼
   Deleted      Memory.delete()           → MemoryDeleted      → DELETED (terminal)
```

Legal status transitions are owned by `MemoryStatus.can_transition_to`: `ACTIVE→{ARCHIVED,DELETED}`, `ARCHIVED→{ACTIVE,DELETED}`, `DELETED→∅`. Any illegal move raises `InvalidMemoryStateError`.

### 8.4 Design decisions

- **Aggregate root + event recording.** `Memory` is the single entry point for state changes; each behavior validates invariants and appends a `DomainEvent` to an internal buffer. The application pulls events (`pull_events`) after the unit of work commits and dispatches them — this is the seam for an outbox/queue later, with zero domain coupling to consumers.
- **Score as an immutable value object.** Evolution produces a *new* `MemoryScore` (`reinforced`, `decayed`) instead of mutating, so every change is explicit and traceable. The weights live as `ClassVar`s and sum to exactly 1.0, which makes the total mathematically guaranteed to be normalized in [0,1].
- **Status owns its own transition table.** Lifecycle rules live in one value object, not scattered across services — a single, testable source of truth.
- **Versions are frozen snapshots.** History must not change; `MemoryVersion.capture()` deep-copies mutable metadata so the past is immutable, and `Memory.rollback_to()` is itself a forward-versioned change (full audit trail).
- **Relations are entities, not attributes.** Edges carry identity and a `weight`, because the graph itself self-evolves (reinforced, weakened, contradicted).
- **Ports speak only domain.** Repository and use-case interfaces reference entities/DTOs and `async` I/O signatures, never a concrete store — preserving the dependency rule.
- **No pydantic in domain/DTOs.** Domain entities and application DTOs are plain dataclasses; pydantic stays at the API boundary. The domain has **zero** third-party imports.

### 8.5 Future extension points

- **New memory types / relation types** — extend the enums; scoring and graph logic are type-agnostic.
- **Pluggable scoring** — the weighted formula is isolated in `MemoryScore`; alternative strategies (learned weights, per-type weights) can be introduced behind the same `calculate_total_score()` contract.
- **Time-based decay** — `MemoryScore.decayed()` defines *how* decay transforms a score; a Stage 5 scheduler decides *when* to apply it.
- **Consolidation & contradiction handling** — `CONTRADICTS` edges + domain events are the hooks for a future LangGraph consolidation workflow to merge/reconcile memories.
- **Event-driven side effects** — the recorded events enable an outbox → queue → graph-sync pipeline without touching the domain.

*Stage 3 implements persistence.*

---

## 9. Stage 3 — Persistence Layer

Stage 3 implements **persistence only** — async SQLAlchemy models, mappers, the
repository implementations behind the Stage 2 ports, a Unit of Work, and Alembic
migrations. **No LangGraph, no embeddings generation, no retrieval, no Neo4j
logic, no API endpoints.**

### 9.1 New files

```
backend/app/
├── infrastructure/database/
│   ├── base.py                 # DeclarativeBase, naming convention, mixins, Vector type
│   ├── session.py              # async engine + session-factory builders
│   ├── mappers.py              # domain <-> model translation
│   ├── unit_of_work.py         # SQLAlchemyUnitOfWork
│   └── models/
│       ├── user.py · memory.py · memory_score.py
│       ├── memory_relation.py · memory_version.py · memory_embedding.py
│       └── __init__.py         # registers all tables on Base.metadata
├── application/interfaces/unit_of_work.py   # UnitOfWork port
└── repositories/
    ├── memory_repository.py            # MemoryRepositoryImpl
    ├── memory_relation_repository.py   # MemoryRelationRepositoryImpl
    └── memory_version_repository.py    # MemoryVersionRepositoryImpl

backend/alembic/
├── env.py · script.py.mako
└── versions/0001_initial_schema.py     # creates all 6 tables + pgvector extension

backend/tests/
├── unit/test_mappers.py
└── integration/test_repositories.py · test_migration.py
```

### 9.2 The persistence flow: Domain → Repository → Mapper → Database

```
   Use case (Stage 4)
        │  speaks domain entities + repository PORTS
        ▼
   Domain entity (Memory)                     ← pure Python, no SQLAlchemy
        │
        ▼
   Repository impl (MemoryRepositoryImpl)      ← implements the Stage 2 port
        │  delegates translation to…
        ▼
   Mapper (memory_to_model / model_to_memory)  ← the ONLY code importing both sides
        │
        ▼
   ORM model (MemoryModel + MemoryScoreModel)  ← SQLAlchemy, persistence detail
        │  via AsyncSession owned by…
        ▼
   Unit of Work (SQLAlchemyUnitOfWork)         ← commit / rollback boundary
        │
        ▼
   PostgreSQL (+ pgvector)
```

The mapper is the crucial seam: because it is the single place that knows both a
`Memory` and a `MemoryModel`, the database schema can change without touching the
domain, and the domain can evolve without a migration unless persistence is
actually affected. Repositories never commit — the **Unit of Work** owns the
transaction, so a multi-entity operation (snapshot a version *and* update the
memory) is atomic.

### 9.3 ER diagram

```
        ┌──────────────┐
        │    users     │
        │ id (PK)      │
        │ email (UQ)   │
        └──────┬───────┘
               │ 1
               │            ┌────────────────────────┐
               │ N          │     memory_scores       │
        ┌──────▼───────┐ 1  │ id (PK)                 │
        │   memories   │────│ memory_id (FK,UQ) ──────┼─┐ 1:1
        │ id (PK)      │ 1  │ importance/utility/...  │ │
        │ user_id (FK) │    └─────────────────────────┘ │
        │ content      │◀─────────────────────────────── ┘
        │ memory_type  │
        │ status       │ 1      ┌───────────────────────────┐
        │ version      │────────│      memory_versions       │  N  (history)
        │ is_promoted  │        │ id (PK)                    │
        │ meta (JSONB) │        │ memory_id (FK)             │
        │ deleted_at   │        │ version_number             │
        └──┬────────┬──┘        │ (memory_id,version) UQ     │
        N  │        │ N         └────────────────────────────┘
   source  │        │ target
        ┌──▼────────▼──────────────┐   ┌────────────────────────────┐
        │     memory_relations      │   │     memory_embeddings       │
        │ id (PK)                   │   │ embedding_id (PK)           │
        │ source_memory_id (FK)     │   │ memory_id (FK)              │
        │ target_memory_id (FK)     │   │ vector  : vector(1536)      │  ← pgvector
        │ relation_type · weight    │   │ model_name                  │
        │ (src,tgt,type) UQ         │   │ (memory_id,model_name) UQ   │
        └───────────────────────────┘   └────────────────────────────┘
```

All tables carry `created_at`/`updated_at`; `users` and `memories` add a
`deleted_at` tombstone for **soft deletion** (a delete sets `deleted_at` + status
`deleted`; queries filter `deleted_at IS NULL`). Every child FK is
`ON DELETE CASCADE` for referential integrity on hard deletes.

### 9.4 Why pgvector exists now, before retrieval

The `memory_embeddings` table and its `vector(1536)` column are created in this
stage even though **nothing writes or searches embeddings yet**. Three reasons:

1. **Schema and migrations are the expensive thing to change later.** Settling
   the table, its foreign key, and the `CREATE EXTENSION vector` now means Stage 4
   adds *data and an index*, not a schema rewrite on a populated production DB.
2. **The extension is an infrastructure decision, not a feature.** Enabling
   pgvector is a migration-level, ops-reviewed change; coupling it to the initial
   schema keeps environment provisioning (local, CI, prod) consistent from day one.
3. **It validates the cross-dialect strategy early.** The `Vector` type degrades
   to JSON `TEXT` on SQLite, so the whole schema — embeddings included — is
   creatable in tests today, proving the design before the embedding model lands.

The column is intentionally inert: a place reserved at the right spot in the data
model so that adding semantic search becomes additive.

### 9.5 Test results

`38 passed` (PyTest, isolated in-memory SQLite via `aiosqlite` + `StaticPool`):

- **Mapper tests** — domain↔model round-trips for Memory (+score), Relation, Version; rehydration emits no events.
- **Repository + UoW tests** — save/get, update (content + score), soft delete hides rows, `search` filtering (type / text / weighted-score threshold), relations & versions persistence, and `rollback` discarding uncommitted work.
- **Migration tests** — revision graph (`0001_initial`, no down-revision), all six `create_table` calls present, `CREATE EXTENSION vector` present, and `Base.metadata` declares the six required tables.

*Stage 4 wires use cases and the API.*

---

## 10. Stage 4 — Application Services & API Layer

Stage 4 connects the domain and persistence layers to the outside world:
concrete use cases, an orchestration service, the HTTP endpoints, Pydantic
validation, dependency wiring, an event dispatcher, and error→HTTP mapping.
**No LangGraph, embeddings, vector search, Neo4j retrieval, or LLM calls.**

### 10.1 New files

```
backend/app/
├── application/
│   ├── exceptions.py                      # ApplicationError, MemoryNotFoundException, MemoryValidationException
│   ├── presenters.py                      # Memory -> response DTO
│   ├── interfaces/event_dispatcher.py     # EventDispatcher port
│   ├── use_cases/memory_use_cases_impl.py # Create/Update/Delete/Search impls
│   └── services/memory_service.py         # orchestration facade
├── infrastructure/events/in_process_dispatcher.py  # InProcessEventDispatcher (+ singleton)
├── schemas/memory.py                      # Create/Update/Search request + Response schemas
└── api/v1/routes/memories.py              # the six endpoints

backend/tests/
├── unit/test_event_dispatcher.py · test_dependencies.py
└── integration/test_use_cases.py · test_api.py
```
Updated: `api/v1/dependencies/providers.py` (event-dispatcher + memory-service providers), `core/exceptions.py` (application/domain error handlers), `api/v1/router.py` (mount memories), `docs/architecture.md`.

### 10.2 Endpoint table

| Method | Path | Body / Params | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/memories` | `CreateMemoryRequestSchema` | **201** | 422 validation |
| GET | `/api/v1/memories/{id}` | path id | **200** | 404 not found |
| PUT | `/api/v1/memories/{id}` | `UpdateMemoryRequestSchema` | **200** | 404, 422, 409 state |
| DELETE | `/api/v1/memories/{id}` | `?user_id=` | **200** | 404 not found |
| POST | `/api/v1/memories/search` | `MemorySearchRequestSchema` | **200** | 422 validation |
| GET | `/api/v1/memories/user/{user_id}` | `?limit=&offset=` | **200** | 422 validation |

Every response uses the standardized envelope: `{ "success", "data" | "error", "request_id" }`.

### 10.3 Request flow

```
   HTTP Request
        │   (JSON validated by a Pydantic *Schema*: content length, metadata limits, enum membership)
        ▼
   FastAPI Router  (api/v1/routes/memories.py)
        │   schema.to_dto()  →  application DTO
        ▼
   MemoryService  (orchestration only — no HTTP, no SQL)
        │   delegates to the use case
        ▼
   Use Case  (CreateMemoryUseCaseImpl, …)
        │   builds/loads a domain entity, enforces invariants
        ▼
   Unit of Work  (transaction boundary: commit / rollback)
        │
        ▼
   Repository  (MemoryRepositoryImpl — implements the port)
        │   mapper: domain ↔ ORM model
        ▼
   Database  (PostgreSQL)
        ▲
        │   after commit → use case pulls recorded domain events →
        └── Event Dispatcher (in-process now; Kafka/RabbitMQ-ready behind the port)
```

### 10.4 Design decisions

- **Use cases own the transaction + events.** Each opens a Unit of Work, mutates the aggregate, commits, then dispatches the events the aggregate recorded — events fire only after durable success, never on a rolled-back change.
- **Service is orchestration-only.** `MemoryService` composes the use cases and exposes the read paths; it holds no SQL (those are behind ports) and no HTTP (that is the router). It is the single injection point the API depends on.
- **Three error tiers, mapped centrally.** Pydantic `RequestValidationError` → 422 (sanitized details), application `MemoryNotFoundException` → 404 / `MemoryValidationException` → 422, and domain `InvalidMemoryStateError` → 409. The application layer stays framework-free; only the API layer knows HTTP.
- **Dispatcher behind a port.** `InProcessEventDispatcher` matches handlers along the event MRO (register on `DomainEvent` for a catch-all) and isolates handler failures. Swapping it for a broker is a one-line composition-root change — no use-case edits.
- **Schemas are the only pydantic.** Validation and the wire contract live at the edge; DTOs and the domain remain plain Python.

### 10.5 Test results

`57 passed` (PyTest). New in Stage 4:

- **Use-case tests** (SQLite UoW + real dispatcher) — create persists + emits `MemoryCreated`; update snapshots the pre-edit version + emits `MemoryUpdated`; missing target → `MemoryNotFoundException`; delete soft-deletes + emits `MemoryDeleted`; search filters.
- **API tests** (TestClient + fake service) — 201 envelope on create; 422 on blank content, bad enum, and empty update; 200/404 get; update bumps version; delete; search & list.
- **Event-dispatcher tests** — matching delivery, MRO catch-all, async handler awaited, failure isolation.
- **DI tests** — dispatcher singleton; `MemoryService` assembled with the full method surface.

*Stage 5 builds the Memory Intelligence Engine.*

---

## 11. Stage 5 — Memory Intelligence Engine

Stage 5 makes memories **evolve**: they are reinforced on reuse, decay over
time, get promoted when valuable, and are archived when stale. This is pure
memory intelligence — **no embeddings, vector search, retrieval, Neo4j, or LLM
calls.**

### 11.1 New files

```
backend/app/
├── application/
│   ├── dto/analytics_dto.py                       # MemoryAnalytics
│   ├── interfaces/scheduler.py                     # Scheduler + ScheduledJob ports (+ future jobs)
│   └── services/
│       ├── intelligence_config.py                  # tunable thresholds
│       ├── decay_strategies.py                     # DecayStrategy + Exponential/Linear
│       ├── memory_intelligence_service.py          # reinforce/decay/promote/archive/evaluate
│       └── memory_analytics_service.py             # counts, average, distribution
├── schemas/analytics.py                            # AnalyticsResponseSchema
└── alembic/versions/0002_add_memory_priority.py    # priority column

Updated: domain (events MemoryReinforced/MemoryDecayed, MemoryPromoted.priority;
MemoryScore.reinforced bumps utility; Memory gains priority, decay(), reinforce
event), persistence (priority column + mappers + analytics query), API
(reinforce/promote/archive/analytics endpoints + providers), DTO/schema priority.
```

### 11.2 Memory evolution

```
            Created                Memory.create()              ACTIVE, score≈neutral, priority 0
               │
               ▼
   ┌──────  Reinforced  ◀── successful reuse ─┐   reinforce(): frequency↑ utility↑, recency→1.0
   │           │                              │   → MemoryReinforced ; refreshes updated_at
   │           ▼                              │
   │        Promoted     total_score ≥ 0.65   │   promote(): is_promoted=True, priority++
   │           │         (stays ACTIVE)       │   → MemoryPromoted
   │           ▼                              │
   └──────   Decayed   ◀── time passes ───────┘   decay(factor): recency × factor
               │                                  → MemoryDecayed ; does NOT touch updated_at
               ▼
            Archived     score < 0.30 AND idle ≥ 30d   archive(): ACTIVE → ARCHIVED
               │                                        → MemoryArchived  (restore() reverses)
               ▼
            Deleted      delete(): → DELETED (terminal, soft-deleted in store)
```

Reinforcement and decay are continuous and can repeat; promotion and archival are
threshold-driven transitions. The cycle is intentionally a loop: a decayed memory
can be reinforced back to relevance before it ever qualifies for archival.

### 11.3 Scoring strategy

A memory's standing is one number, `total_score ∈ [0, 1]`, a fixed weighted sum
of five normalized signals (weights sum to 1.0, so the result is always
normalized):

| Signal | Weight | Meaning | Moved by |
| --- | --- | --- | --- |
| importance | 0.30 | intrinsic significance | set on creation, slow to change |
| utility | 0.25 | how useful when reused | **reinforce** (↑) |
| frequency | 0.20 | how often reused | **reinforce** (↑) |
| recency | 0.15 | how recently touched | **reinforce** (→1.0) / **decay** (×factor) |
| confidence | 0.10 | how sure it is correct | extraction/consolidation (future) |

The intelligence policy reads this score against tunable thresholds
(`IntelligenceConfig`): **promotion** needs `total_score ≥ promotion_threshold`
(0.65); **archival** needs `total_score < archival_score_threshold` (0.30) **and**
idle ≥ `archival_max_idle_days` (30). Decay is governed by an injectable
`DecayStrategy` — `ExponentialDecayStrategy` (half-life) by default, or
`LinearDecayStrategy` — so the recency curve is configurable without touching the
engine. Decay is measured against `updated_at` and deliberately doesn't update it,
so repeated sweeps keep measuring true idle age.

### 11.4 Endpoints added

| Method | Path | Effect |
| --- | --- | --- |
| POST | `/api/v1/memories/{id}/reinforce?user_id=&step=` | raise frequency + utility |
| POST | `/api/v1/memories/{id}/promote?user_id=` | flag + priority (409 if below threshold) |
| POST | `/api/v1/memories/{id}/archive?user_id=&force=` | ARCHIVE (422 if not eligible) |
| GET | `/api/v1/memories/analytics?user_id=` | counts, average score, distribution |

### 11.5 Future scheduler design

The evolution operations above are per-memory and synchronous today. At scale
they run as recurring background sweeps, defined now as **ports only**
(`app/application/interfaces/scheduler.py`):

- **`DecaySweepJob`** — nightly; apply `decay_memory` across active memories.
- **`ArchivalSweepJob`** — periodic; archive every memory where `should_archive` holds.
- **`PromotionSweepJob`** — periodic; promote memories that have crossed the threshold.

A concrete `Scheduler` (APScheduler / Celery beat / Kubernetes CronJob) will
implement `register(job, cron)` / `start` / `stop` and invoke the same
`MemoryIntelligenceService` methods the API uses — no new business logic, just a
trigger. Each job is an independent unit, so they can be sharded by user/tenant
and run on separate workers as volume grows.

### 11.6 Test results

`92 passed` (target was 75+). New in Stage 5:

- **Decay strategies** — exponential half-life (1.0 at 0, 0.5 at half-life, monotonic), linear bleed-off + clamping, validation.
- **Domain evolution** — reinforce raises frequency/utility + emits event + refreshes `updated_at`; decay lowers recency + emits event + leaves `updated_at`; promote increments priority; guards.
- **Intelligence service** (SQLite + dispatcher) — reinforce, promote (incl. below-threshold 409 path), decay (recency ×0.5 at half-life), archive (eligible / not-eligible / force), evaluate.
- **Analytics** — empty, mixed counts + distribution, per-user scoping.
- **Intelligence API** — reinforce/promote/archive/analytics happy paths + 404/409/422 mappings.
- **Scheduler** — abstractions are abstract; future jobs declared with names.

*Stage 6 builds the embedding pipeline.*

---

## 12. Stage 6 — Embedding Pipeline

Stage 6 generates and stores embeddings for memories, driven by domain events.
It is **generation + storage + lifecycle only** — **no retrieval, hybrid/vector
search, Neo4j, RAG, or LLM chat.** The `memory_embeddings` table (reserved in
Stage 3) is now populated.

### 12.1 New files

```
backend/app/
├── application/
│   ├── dto/embedding_dto.py                        # EmbeddingRecord
│   ├── interfaces/
│   │   ├── embedding_provider.py                   # EmbeddingProvider port
│   │   └── embedding_job_processor.py              # EmbeddingJob + processor port
│   └── services/
│       ├── embedding_service.py                    # generate/store/update/delete + job processing
│       └── embedding_event_handler.py              # memory events -> embedding jobs
├── infrastructure/embeddings/
│   ├── deterministic_provider.py                   # offline dev/test provider
│   ├── openai_provider.py                          # OpenAIEmbeddingProvider
│   ├── bge_provider.py                             # LocalBGEEmbeddingProvider
│   ├── factory.py                                  # provider selection from config
│   └── in_process_processor.py                     # async in-process worker
├── repositories/memory_embedding_repository.py     # MemoryEmbeddingRepositoryImpl
└── alembic/versions/0003_add_embedding_dimensions.py

Updated: config (embedding settings), MemoryEmbeddingModel (+dimensions), mappers,
UnitOfWork (+embeddings repo), providers/health (+embedding provider), main lifespan
(wires the event-driven pipeline + drains on shutdown).
```

### 12.2 Embedding flow (event-driven)

```
   Memory                      use case mutates the aggregate, commits,
     │                         then dispatches the recorded domain event
     ▼
   Event        MemoryCreated / MemoryUpdated  ── or ──  MemoryDeleted
     │                         │                              │
     ▼                         ▼                              ▼
   EmbeddingEventHandler   submit UPSERT job             submit DELETE job
     │                          (EmbeddingJobProcessor — async, in-process now)
     ▼
   EmbeddingService        load memory → provider.embed_text(content) → EmbeddingRecord
     │
     ▼
   EmbeddingRepository     save_embedding (upsert by memory_id + model_name)
     │
     ▼
   pgvector  (memory_embeddings: vector, model_name, dimensions, created_at)
```

Producers never call the embedding pipeline directly — they only record domain
events, so the coupling is one-way and the whole pipeline is swappable. Work runs
off the request path on the job processor; failures are isolated and logged.

### 12.3 Provider comparison

| Provider | Use | Dimensions | Cost / Deps | Notes |
| --- | --- | --- | --- | --- |
| **DeterministicEmbeddingProvider** (`hash`) | dev / tests | configurable (1536) | none, offline | reproducible, **not** semantic |
| **OpenAIEmbeddingProvider** (`openai`) | production | 1536 (text-embedding-3-small) | API key, per-call cost | client lazily imported/injected |
| **LocalBGEEmbeddingProvider** (`bge`) | self-hosted | 384–1024 (model-dependent) | GPU/CPU + `sentence-transformers` | no per-call cost; different dims ⇒ migration |

Selection is config-driven (`EMBEDDING_PROVIDER`); the factory returns a
process-wide singleton. All implement one `EmbeddingProvider` port
(`embed_text`, `embed_batch`, `model_name`, `dimensions`, `health_check`).

### 12.4 Embedding versioning & model-migration strategy

Each row records **`model_name`**, **`dimensions`**, and **`created_at`** — so
every vector is attributable to the exact model that produced it. Storage is keyed
on `(memory_id, model_name)`, which means multiple model generations can coexist
during a migration.

Migrating to a new embedding model is therefore additive and safe:

1. **Add a column / index** for the new dimensionality if it differs (pgvector
   columns are fixed-width; e.g. OpenAI 1536 → BGE 1024 needs a matching column).
2. **Dual-write**: point the provider at the new model; new/updated memories embed
   under the new `model_name` while old rows remain valid.
3. **Backfill**: a `DecaySweep`-style background job (Stage 5 scheduler ports)
   re-embeds existing memories into the new model via the same `UPSERT` path.
4. **Cut over** reads to the new `model_name`, then drop the old rows/column.

No memory data is lost and no downtime is required, because the embedding is
derived data the pipeline can always regenerate from `Memory.content`.

### 12.5 Background processing

`EmbeddingJobProcessor` is a port; Stage 6 ships `InProcessEmbeddingJobProcessor`
(asyncio tasks in the app's loop, with `drain()` for graceful shutdown/tests).
Because producers depend only on the port, swapping to **Celery**, **RQ**, or a
**Kafka consumer** at scale requires no change to the event handler or use cases —
only a different processor wired at the composition root.

### 12.6 Health

`GET /api/v1/health` now also reports `embedding_provider` (`up`/`down`). It is
informational — a degraded embedding provider does not flip the overall liveness
to 503, since embedding is asynchronous and non-blocking for core reads/writes.

### 12.7 Test results

`119 passed` (target 110+). New in Stage 6:

- **Providers** — deterministic (reproducible, dims, range, batch, validation), OpenAI (injected fake client, health from config, missing-key error), BGE (injected fake model), and config-driven factory selection.
- **Job processor** — submit runs the job, `drain` awaits many, failures isolated.
- **Repository** — save/get, upsert-on-save, update, delete, missing→None.
- **Service** — generate, store, update (vector changes with content), delete, job UPSERT/DELETE, missing-memory no-op.
- **Event integration** — `MemoryCreated`/`MemoryUpdated` → embedding stored; `MemoryDeleted` → embedding removed.

*Stage 7 builds the hybrid retrieval engine.*

---

## 13. Stage 7 — Hybrid Retrieval Engine

Stage 7 retrieves memories by blending semantic similarity, lexical matching,
memory-intelligence value, and recency, then reranks. **Retrieval only** — **no
LangGraph, LLM calls, RAG response generation, or Neo4j graph traversal.**

### 13.1 New files

```
backend/app/
├── application/
│   ├── dto/retrieval_dto.py                        # MemorySearchQuery, RetrievedMemory, RetrievalResult, ScoreBreakdown
│   ├── interfaces/reranker.py                       # Reranker port
│   └── services/retrieval/
│       ├── config.py                                # RetrievalConfig (all weights)
│       ├── scoring.py                               # cosine, recency, memory-boost, filters
│       ├── bm25.py                                  # Okapi BM25 + tokenizer
│       ├── vector_retriever.py                      # VectorRetriever (cosine)
│       ├── keyword_retriever.py                     # KeywordRetriever (BM25)
│       ├── hybrid_retriever.py                      # HybridRetriever (weighted fusion)
│       ├── reranker.py                              # SimpleCrossEncoderReranker
│       └── retrieval_service.py                     # MemoryRetrievalService (pipeline)
├── schemas/retrieval.py                             # request/response schemas
└── api/v1/routes/retrieval.py                       # POST /retrieval/search, /retrieval/debug

Updated: MemoryEmbeddingRepository (+list_candidates), providers (retrieval DI), router.
```

### 13.2 Retrieval architecture

```
                    Query (text, user_id, filters, top_k)
                                  │
              ┌───────────────────┴───────────────────┐   (run concurrently)
              ▼                                         ▼
       Vector Search                              BM25 Search
   embed query → cosine vs.                  tokenize → Okapi BM25 over
   stored embeddings (pgvector)              content + metadata
              │                                         │
              └───────────────────┬───────────────────┘
                                  ▼
                            Fusion (HybridRetriever)
        union candidates; normalize; weighted blend with
        Memory-Intelligence boost + Recency boost
                                  │
                                  ▼
                         Reranking (Reranker port)
              SimpleCrossEncoderReranker (lexical-overlap heuristic;
              swappable for Cohere / BGE / cross-encoder)
                                  │
                                  ▼
                      Results (top_k)  /  Debug (all + breakdown)
```

The vector and keyword stages run **concurrently** (`asyncio.gather`), each on its
own Unit of Work, so fusion waits only on the slower of the two.

### 13.3 Scoring formula & weighting strategy

```
final = w_vector·vector_score
      + w_bm25·bm25_score
      + w_memory·memory_score
      + w_recency·recency_score
```

Defaults: **vector 0.50, bm25 0.20, memory 0.20, recency 0.10** — semantic
similarity leads (it generalizes beyond exact words), lexical matching anchors
exact terms/IDs, and the memory/recency boosts act as tie-breakers that let
high-value or fresh memories win close calls. All weights live in
`RetrievalConfig` and are injected, so they can be tuned per environment/tenant.

Per-signal definitions (each normalized to [0, 1] before weighting):

- **vector_score** — cosine(query, memory embedding), clamped to [0, 1].
- **bm25_score** — Okapi BM25 over content + metadata, **min-max normalized** across the candidate set (so it is comparable to the other signals regardless of corpus scale).
- **memory_score** — `(0.4·importance + 0.3·utility + 0.3·frequency)` plus a promotion bonus (+0.15) and a priority bonus (up to +0.10), clamped to [0, 1]. This is where **Memory Intelligence (Stage 5)** boosts ranking.
- **recency_score** — exponential decay `0.5^(age_days / half_life)` (default half-life 30 days) over `updated_at`.

**Reranking** then multiplies the fused score by `(1 + overlap_weight · lexical_overlap)` and re-sorts — a cheap, deterministic stand-in until a learned cross-encoder is plugged in behind the `Reranker` port.

### 13.4 Candidate union & normalization

Vector and keyword retrievers each return up to `candidate_pool` (default 50)
hits; fusion takes their **union** by memory id. A memory found only by vector
gets `bm25_score = 0`; one found only by BM25 gets `vector_score = 0`. BM25 is
min-max normalized within the union so a large lexical score cannot dwarf the
bounded [0,1] signals. Default filters restrict to `ACTIVE` memories unless the
query overrides `statuses`.

### 13.5 API

| Method | Path | Returns |
| --- | --- | --- |
| POST | `/api/v1/retrieval/search` | ranked top_k results |
| POST | `/api/v1/retrieval/debug` | every reranked candidate with the full `ScoreBreakdown` (vector, bm25, memory, recency, final) |

### 13.6 Production note (pgvector)

`VectorRetriever` scores cosine over candidates fetched via the repository port.
At small/medium scale this is exact and simple; at large scale the
`list_candidates` port is the seam to push the search into a **pgvector ANN
index** (`ORDER BY embedding <=> :q LIMIT k`) without changing the retriever,
fusion, or service.

### 13.7 Test results

`151 passed` (target 140+). New in Stage 7:

- **Scoring** — cosine (identical/orthogonal/opposite/degenerate), recency decay, memory boost (promotion + priority), filters.
- **BM25** — tokenization, match vs. no-match, term-frequency ranking, empty edge cases.
- **Reranker** — overlap boost reorders, empty query preserves order, breakdown updated.
- **Vector / Keyword retrievers** — semantic closest first, metadata search, limits, filters.
- **Hybrid fusion** — relevant-first, candidate union, weight changes alter ranking.
- **Retrieval service** — end-to-end search (top_k + relevant first), debug (all + breakdown).
- **API** — search/debug envelopes, score breakdown exposed, empty-query 422, filters accepted.

*Stage 8 builds the context assembly engine.*

---

## 14. Stage 8 — Context Assembly Engine

Stage 8 turns retrieved memories into a single, token-budgeted **context
package** ready to hand to an LLM. **Context construction only** — **no
LangGraph, no LLM calls, no chat generation, no Neo4j traversal.**

### 14.1 New files

```
backend/app/
├── application/
│   ├── dto/context_dto.py                          # ContextRequest, ContextMemory, ContextPackage, debug DTOs
│   ├── interfaces/
│   │   ├── token_counter.py                        # TokenCounter port
│   │   └── context_compressor.py                   # ContextCompressor port
│   └── services/context/
│       ├── config.py                               # ContextConfig
│       ├── tokenization.py                         # HeuristicTokenCounter (~4 chars/token)
│       ├── selection_service.py                    # MemorySelectionService (budget + priority)
│       ├── conflict_detector.py                    # ConflictDetector (negation contradiction)
│       ├── consolidation_service.py                # MemoryConsolidationService (dedupe)
│       ├── compressor.py                           # HeuristicContextCompressor
│       └── context_builder.py                      # ContextBuilderService (pipeline)
├── schemas/context.py
└── api/v1/routes/context.py                         # POST /context/build, /context/debug

Updated: RetrievedMemory (+is_promoted/priority), hybrid retriever, providers, router.
```

### 14.2 Context assembly architecture

```
                       Query (text, user_id, filters, max_tokens, top_k)
                                          │
                                          ▼
                          Retrieval  (Stage 7 hybrid engine → ranked RetrievedMemory)
                                          │
                                          ▼
                          Selection  (promoted-first, score-ordered;
                                      greedy fill under the token budget)
                                          │
                                          ▼
                          Consolidation  (drop near-duplicates; keep the
                                          highest-scored representative)
                                          │
                                          ▼
                          Conflict Detection  (flag negation contradictions)
                                          │
                                          ▼
                          Compression  (whitespace normalize; prune to budget;
                                        render context_text)
                                          │
                                          ▼
                          Context Package  (memories + context_text + token stats)
```

`debug` exposes the full provenance at every stage: selected, dropped (with
reason), conflicts, consolidations, and compression stats.

### 14.3 Token-budget strategy

The budget (`max_tokens`) is enforced in two complementary places:

1. **Selection (primary gate).** Candidates are ordered **promoted-first, then by
   retrieval score**, and admitted greedily while they fit. This guarantees the
   highest-value memories occupy the budget first; ones that don't fit are
   dropped with reason `token_budget`. Greedy-by-priority (rather than strict
   prefix) lets a small lower-ranked memory use leftover budget a large one
   couldn't.
2. **Compression (final guarantee).** After consolidation removes redundancy,
   the compressor normalizes whitespace (free savings) and, if anything still
   exceeds the budget, prunes the lowest-scored memories — so the emitted package
   is *always* within `max_tokens`.

Tokens are estimated by a `HeuristicTokenCounter` (~4 chars/token) behind the
`TokenCounter` port; swap in tiktoken for model-exact budgeting with no logic
change.

### 14.4 Compression strategy

`HeuristicContextCompressor` (no LLM):

1. **Whitespace normalization** — collapse repeated whitespace per memory;
   lossless token savings.
2. **Budget pruning** — sort by score and drop the lowest until within budget
   (reason `compression`).
3. **Rendering** — emit `- (type) content` lines as `context_text`.

It reports `original_tokens`, `compressed_tokens`, `ratio`, and
`removed_memories`. A future `LLMCompressor` (summarization) implements the same
`ContextCompressor` port — the builder is unaffected.

### 14.5 Conflict detection & consolidation

- **Conflict** — two memories with high overlap of *significant* terms (stopwords
  and negation markers removed) where **exactly one is negated** ⇒
  `negation_contradiction` (e.g. "I use Python" vs "I no longer use Python").
  Conflicts are *reported*, not auto-resolved (resolution is a future, possibly
  LLM-assisted, step).
- **Consolidation** — memories are compared by token Jaccard; near-duplicates
  (≥ 0.85) collapse to the **highest-scored** representative, recorded in a
  `ConsolidationRecord`.

### 14.6 API

| Method | Path | Returns |
| --- | --- | --- |
| POST | `/api/v1/context/build` | the `ContextPackage` (memories + context_text + token totals) |
| POST | `/api/v1/context/debug` | package **plus** selected, dropped (reasons), conflicts, consolidations, compression stats |

### 14.7 Test results

`182 passed` (target 170+). New in Stage 8:

- **Token counter** — empty, scaling, 4-chars/token.
- **Selection** — score ordering, promoted-first, budget drop, leftover-fill, empty.
- **Conflict detection** — negation contradiction, both-positive/both-negated no-conflict, unrelated, single.
- **Consolidation** — duplicate merge keeps best, distinct kept, reason, empty.
- **Compression** — within-budget keeps all, whitespace savings, over-budget prune, rendered text, empty ratio.
- **Context builder** (SQLite + real retrieval) — package within budget, small-budget enforcement, conflicts reported, duplicate consolidation.
- **API** — build/debug envelopes, full debug provenance, empty-query and invalid-budget 422.

*Stage 9 (below) adds the **knowledge graph** — graph memory, relationship
derivation, traversal, and graph-aware retrieval. The **LangGraph**
extraction/consolidation workflows are a separate, later effort (Stage 10), not
part of Stage 9.*

---

## 15. Stage 9 — Knowledge Graph Layer

Stage 9 adds **graph memory**: each memory becomes a node, edges are derived
between related memories, and hybrid retrieval can be **expanded** along those
edges. It is **graph only** — **no LangGraph, no LLM calls, no agent workflows.**
Relationship derivation is lexical (shared significant entities), not learned.

### 15.1 Files

```
backend/app/
├── application/
│   ├── dto/graph_dto.py                          # GraphNode/Edge/Path, ExpandedMemory, GraphAwareResult
│   ├── interfaces/
│   │   ├── graph_repository.py                   # GraphRepository port (nodes/edges/traversal)
│   │   └── graph_job_processor.py                # GraphJobProcessor port + GraphSyncJob (background sync)
│   └── services/graph/
│       ├── config.py                             # GraphConfig (derivation, sync bound, expansion allowlist)
│       ├── mapping.py                            # memory_to_node + lexical entity extraction
│       ├── relationship_service.py               # derive RELATED_TO/SUPPORTS/USED_IN edges
│       ├── sync_service.py                       # upsert node + re-derive edges (bounded); job API
│       ├── event_handler.py                      # memory events -> graph-sync jobs
│       ├── traversal_service.py                  # neighbors / subgraph / paths / expand
│       └── graph_aware_retrieval.py              # hybrid -> graph expansion (filtered, provenance-tagged)
├── infrastructure/graph/
│   ├── neo4j.py                                  # Neo4jManager (+ public `database`)
│   ├── neo4j_graph_repository.py                 # Cypher-backed GraphRepository
│   ├── in_memory_graph_repository.py             # offline/dev default (adjacency)
│   ├── in_process_processor.py                   # InProcessGraphJobProcessor (async, drainable)
│   └── factory.py                                # backend selection (GRAPH_BACKEND)
├── schemas/graph.py                              # pydantic wire schemas
└── api/v1/routes/graph.py                         # /graph/search|traverse|memory/{id}|debug

backend/tests/
├── unit/        test_in_memory_graph_repository · test_graph_relationship_service · test_graph_traversal_service
└── integration/ test_graph_sync · test_graph_events · test_graph_aware_retrieval · test_graph_api · test_neo4j_graph_repository
```

### 15.2 Node & edge model

A memory maps to **one** `GraphNode` (`node_id = str(memory.id)`), whose
`node_type` is derived from `MemoryType` and whose `properties` carry
`content`, `memory_type`, `status`, `user_id`, `score`, `is_promoted` — enough
for graph-aware retrieval to build results **without extra DB calls**. Edges
(`GraphEdge`) are typed (`GraphEdgeType`), directed, and weighted (shared/union
entity ratio). Edge type is chosen by configurable type-pair rules
(GOAL/PROJECT→`SUPPORTS`, SKILL/PROJECT→`USED_IN`, …), defaulting to
`RELATED_TO`.

### 15.3 Sync flow (event-driven, off the request path)

```
   Memory mutated → use case commits → MemoryCreated/Updated/Deleted dispatched
        │
        ▼
   GraphEventHandler ── submits ──▶ GraphJobProcessor (async, in-process; drainable)
        │                                   │  SYNC | REMOVE
        ▼                                   ▼
   GraphSyncService.process ──▶ sync_memory / remove_memory
        sync: upsert node → DELETE existing incident edges → derive vs. bounded
              candidate set → create fresh edges
```

Three properties make this scale- and correctness-safe:

1. **Off the request path.** Like the Stage 6 embedding pipeline, sync runs on a
   background `GraphJobProcessor` (the `GraphSyncJob` is submitted, not awaited
   inline), drained on shutdown. Swapping in Celery/RQ/Kafka is a composition-root
   change behind the same port.
2. **Bounded derivation (no O(N²)).** Edges are derived against the most recent
   `GraphConfig.max_sync_candidates` (default 50) of the user's memories
   (via `list_by_user`), so a single write is O(K), not O(N) in corpus size.
3. **Re-derivation removes stale edges.** On every sync the node's existing edges
   are deleted before fresh ones are written, so an edited memory never leaves a
   stale relationship behind. (`GraphSyncService` is the only edge writer.)

### 15.4 Graph-aware retrieval

```
   Query → Hybrid Retrieval (Stage 7) → Graph Expansion → ranked ExpandedMemory[]
```

Direct hits keep provenance `hybrid` and their retrieval score. Each hit's
neighbors are pulled in and tagged provenance `graph`, scored at a decayed
fraction (`graph_score_decay`, default 0.5) of the seed's score so expansion
adds context without outranking direct matches. Expansion is **filtered**:

- **Edge-type allowlist** (`GraphConfig.expansion_edge_types`) — `CONTRADICTS`
  is excluded so a contradicting memory is never surfaced as supporting context.
- **Tenant isolation** — a neighbor whose `user_id` ≠ the query's is dropped.
- **Status filter** — only `ACTIVE` neighbors expand (or the query's explicit
  `statuses`).

### 15.5 Backends

`GraphRepository` has two adapters, selected by `GRAPH_BACKEND`:

- **`InMemoryGraphRepository`** (`memory`, default) — adjacency maps; offline,
  dependency-free; the test/dev default and the basis of the in-memory suite.
- **`Neo4jGraphRepository`** (`neo4j`) — Cypher over the async driver owned by
  `Neo4jManager`. Nodes share a `:MemoryNode` label keyed by `id`; edge types
  come from the validated `GraphEdgeType` enum. `get_edges` reports the **true**
  stored direction (`startNode`/`endNode`) so a directional `delete_edge` always
  matches — the seam that makes §15.3's re-derivation correct on Neo4j too.

The backends mirror each other's semantics, so services behave identically
regardless of which is wired in.

### 15.6 API

| Method | Path | Returns |
| --- | --- | --- |
| POST | `/api/v1/graph/search` | graph-aware results (hybrid + expansion) |
| POST | `/api/v1/graph/debug` | same, with `hybrid_count` / `graph_count` |
| POST | `/api/v1/graph/traverse` | depth-limited subgraph from a node |
| GET | `/api/v1/graph/memory/{id}` | a memory's node + immediate neighbors/edges |

### 15.7 Tests

Unit: in-memory repository, relationship derivation, traversal. Integration:
`GraphSyncService` (node/edge derivation, stale-edge removal, bounded scan,
delete), event→job wiring, graph-aware expansion + filtering, the `/graph/*`
API, and a **live Neo4j** suite that **skips when no server is reachable** (so
offline CI stays green). The Neo4j path is verified against a real server via
`docker compose up neo4j`.

*Stage 10 (Phase 1, below) adds the LangGraph **memory extraction** workflow on
top of this graph and the Stage 8 context package.*

---

## 16. Stage 10 (Phase 1) — LangGraph Memory Extraction

Stage 10 Phase 1 turns **raw conversation/document text into structured memories**
via a LangGraph workflow. It is **extraction ingestion only** — **not** a chat
agent, RAG runtime, query-time workflow, consolidation workflow, or LLM
compressor (those are later phases). The workflow produces **DTOs**; every memory
is then created through the existing `CreateMemoryUseCase`, so embeddings and
graph sync follow automatically.

```
   Conversation / document text
            │  POST /api/v1/ingest  -> 202 + job_id (async)
            ▼
   LangGraph Extraction Workflow  (infrastructure/llm/graphs)
     signal detection → candidate extraction → type classification
        → importance estimation → confidence estimation → validation
            │  List[ExtractedMemory]  (DTOs only — no LangGraph type escapes)
            ▼
   IngestMemoryUseCase  ──per memory──▶  CreateMemoryUseCase   (the single write path)
            │                                   │  commit → MemoryCreated
            ▼                                   ▼
        IngestSummary                     Domain Events
                                                │
                                  ┌─────────────┴─────────────┐
                                  ▼                           ▼
                         Embedding pipeline            Graph sync
                         (pgvector)                    (Neo4j / in-memory)
```

### 16.1 Files

```
backend/app/
├── application/
│   ├── interfaces/
│   │   ├── llm_provider.py              # LLMProvider port (generate / structured_generate)
│   │   ├── workflow_engine.py           # WorkflowEngine port (extract_memories -> ExtractionResult)
│   │   └── workflow_job_processor.py    # WorkflowJobProcessor port + WorkflowJob
│   ├── dto/extraction_dto.py            # ExtractionRequest, ExtractedMemory, ExtractionResult, IngestSummary
│   └── use_cases/ingest_memory_use_cases.py(+_impl)   # IngestMemoryUseCase -> CreateMemoryUseCase
├── infrastructure/llm/
│   ├── providers/{deterministic,openai,anthropic}_provider.py + factory.py
│   ├── graphs/extraction_steps.py       # 6 shared steps + ExtractionState + WORKFLOW_VERSION
│   ├── graphs/sequential_engine.py      # offline default engine (no LangGraph)
│   ├── graphs/extraction_graph.py       # LangGraphExtractionEngine (lazy `import langgraph`)
│   ├── graphs/factory.py                # engine selection (WORKFLOW_ENGINE)
│   └── in_process_workflow_processor.py # InProcessWorkflowJobProcessor (async, drainable)
├── schemas/ingest.py                    # IngestRequestSchema / IngestAcceptedSchema
└── api/v1/routes/ingest.py              # POST /ingest (202 Accepted)
```

### 16.2 Provider architecture

`LLMProvider` is a port (`generate`, `structured_generate(prompt, schema)`,
`model_name`, `health_check`) — the application/workflow layer never imports an
SDK. Adapters: **`DeterministicLLMProvider`** (offline default; reproducible,
rule-based structured output so the pipeline runs with no keys), and
**`OpenAIProvider`** / **`AnthropicProvider`** (lazy SDK imports; only required
when selected). Selection is config-driven (`LLM_PROVIDER`, default
`deterministic`) via a cached factory — the same pattern as the embedding
provider.

### 16.3 Workflow architecture

`WorkflowEngine.extract_memories(ExtractionRequest) -> ExtractionResult` is the
port. The six steps live once in `extraction_steps.py` (provider-driven) and are
shared by two engines so they never diverge:

- **`SequentialExtractionEngine`** — runs the steps in order; **no LangGraph
  dependency**; the offline/dev/test default (`WORKFLOW_ENGINE=sequential`).
- **`LangGraphExtractionEngine`** — wires the same steps as nodes of a LangGraph
  `StateGraph` (`langgraph` imported lazily); production
  (`WORKFLOW_ENGINE=langgraph`).

`ExtractionResult.workflow_version` (`extraction-v1`) tags every run so future
workflow generations can be traced and compared; it is also written into each
created memory's metadata.

### 16.4 Ingestion architecture

`POST /api/v1/ingest {user_id, text}` returns **202 Accepted** `{job_id,
status:"queued"}` immediately and submits a `WorkflowJob` to an
`InProcessWorkflowJobProcessor` (async, drained on shutdown — identical to the
embedding/graph processors). The processor runs `IngestMemoryUseCase`: it calls
the workflow, then creates each `ExtractedMemory` via **`CreateMemoryUseCase`**
(a fresh Unit of Work per memory), mapping `importance`/`confidence` onto the
memory's `MemoryScore` through the (newly extended, backward-compatible)
`CreateMemoryRequest`. **LangGraph never writes to repositories, the database,
embeddings, or Neo4j** — it only returns DTOs; all persistence and side effects
go through the existing write path and event pipeline.

### 16.5 Tests

Unit (deterministic provider, sequential workflow, job processor) + integration
(ingest use case end-to-end through the event pipeline → embeddings + graph;
`/ingest` API contract). A LangGraph engine suite `importorskip`s `langgraph`
(skips offline, like the live-Neo4j suite) and asserts the graph engine produces
the same memories as the sequential engine. All offline — no API keys, no network.

---

## 17. Stage 10 (Phase 3) — LLM Context Compression

Stage 10 Phase 3 adds an **optional LLM compressor** to the Stage 8 context
assembly pipeline. It is **not** a chat agent, query-time reasoner, or RAG
generator — it sits at exactly one point in the existing pipeline, replacing the
final compression step with an LLM summarization that is **validated and
fallback-guarded**. The heuristic compressor remains the offline default.

```
   Retrieval → Selection → Conflict Detection → Consolidation
        → LLM Compression (validated; heuristic fallback) → Context Package
```

### 17.1 Files

```
backend/app/
├── application/
│   ├── interfaces/context_compressor.py        # port: compress() is now async
│   └── services/context/
│       ├── compressor.py                        # HeuristicContextCompressor (async, unchanged body)
│       └── context_builder.py                   # awaits compressor.compress()
└── infrastructure/llm/compressors/
    ├── compression_prompts.py                   # system prompt + structured prompt builder
    ├── compression_validation.py                # 5-check output validator
    ├── llm_compressor.py                         # LLMContextCompressor
    └── factory.py                                # build_context_compressor (CONTEXT_COMPRESSOR)

backend/tests/
├── unit/        test_compression_prompts · test_compression_validation
│                test_llm_compressor · test_compressor_factory
│                (test_compression updated: async)
└── integration/ test_llm_context_builder
```

### 17.2 Async port conversion

The `ContextCompressor` port's `compress()` became **`async`** so an
implementation may call an `LLMProvider`. The blast radius is minimal: the
`HeuristicContextCompressor` body is unchanged (it simply no longer needs to be
sync), and `ContextBuilderService._assemble()` gains one `await`. All existing
DTOs (`CompressionResult`, `CompressionStats`, `ContextPackage`) and the
`/context/build` · `/context/debug` API contracts are **unchanged**.

### 17.3 Provider architecture

`LLMContextCompressor` reuses the **Stage 10 Phase 1 `LLMProvider` port** — the
same `DeterministicLLMProvider` (offline default), `OpenAIProvider`, and
`AnthropicProvider` adapters, selected by the existing `LLM_PROVIDER` setting. No
SDK is imported outside `infrastructure/`. Selection of the compressor itself is
config-driven via `CONTEXT_COMPRESSOR` (`heuristic` default, or `llm`) through a
cached factory — the same pattern as the embedding and LLM provider factories.

### 17.4 Prompt architecture

`compression_prompts.py` builds a **deterministic, structured** prompt: a fixed
system prompt that mandates preservation of facts/goals/preferences/projects and
**both sides of any contradiction**, and a user prompt that renders each memory
as a `[TYPE] (score) content` line and states an explicit character budget
(`max_tokens × 4`, matching the heuristic token counter's ratio). The budget in
the prompt is a *steer*, never the guarantee — the guarantee is the
post-generation token validation.

### 17.5 Output validation (never trust the LLM)

Before an LLM response is accepted, `compression_validation.py` runs five checks
in order; the **first failure** routes to the fallback:

1. **parse** — non-empty, textual response.
2. **token** — `count(output) ≤ max_tokens` (the hard budget guarantee).
3. **required-section** — every input memory type's `[TYPE]` marker is present.
4. **contradiction preservation** — every *negated* memory (a contradiction
   signal, detected with the `ConflictDetector` negation vocabulary) keeps at
   least one significant term in the output, so a disagreement can never be
   silently summarized away.
5. **goal preservation** — every `GOAL` memory keeps at least one significant
   term in the output.

"Significant term" reuses the `ConflictDetector` stopword/negation vocabulary, so
validation and conflict detection agree on what is meaningful.

### 17.6 Fallback strategy (context generation can never fail)

```
provider raises ─────────────┐
empty / parse failure ───────┤
budget exceeded ─────────────┼──▶ await HeuristicContextCompressor.compress(...)
missing section ─────────────┤
contradiction/goal dropped ──┘
```

The fallback is the deterministic `HeuristicContextCompressor`: no I/O, always
terminates, always produces output within budget (it prunes). Because the
`DeterministicLLMProvider` echoes its prompt (which exceeds any real budget),
the **offline default path always exercises the fallback** — so tests and dev
run fully offline with the same budget guarantee as Stage 8.

### 17.7 Provenance preservation

On the accepted LLM path the returned `CompressionResult` carries the **original
`ContextMemory` objects** (their `memory_id` and `memory_type` intact) and drops
nothing (`removed=[]`). Conflict records and consolidation records are produced
*upstream* by the builder (before compression) and are unaffected by the
compressor choice, so the `/context/debug` provenance is identical for both
compressors.

### 17.8 Token-budget guarantee

Enforced in the same two places as Stage 8 — **selection** (greedy budget fill)
and **compression** (final guarantee). On the LLM path the final guarantee is the
token-validation check: any response over `max_tokens` is rejected in favor of the
heuristic, which always fits. So `ContextPackage.total_tokens ≤ max_tokens`
**always** holds, regardless of compressor.

### 17.9 Tests

Unit: prompt construction, each of the five validators, and the compressor's
accept/validate/fallback branches (empty response, provider exception, budget
exceeded, missing section, dropped contradiction, dropped goal, budget guarantees
on both paths, deterministic-provider fallback, provenance). Factory:
config-driven selection (`heuristic`/`llm`, case-insensitive, fallback wired).
Integration: the full builder pipeline with the LLM compressor — valid LLM
output, graceful fallback on error, end-to-end budget enforcement, debug stats,
and provenance survival. All offline (fake/deterministic providers; no network).
