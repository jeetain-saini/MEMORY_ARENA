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

*Stage 0 establishes the skeleton these invariants protect. Stage 1 begins filling the domain layer.*
