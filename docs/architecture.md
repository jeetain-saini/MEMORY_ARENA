# MemoryArena — Architecture

**Status:** Stage 0 (Foundation) · **Audience:** Engineers, architects, reviewers
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

*Stage 5 would introduce embeddings, vector/graph retrieval, and the LangGraph extraction/consolidation workflows.*
