# MemoryArena Project Handoff

> **Purpose of this document.** A self-contained state-of-the-world for any future
> Claude Code session (or human engineer) continuing MemoryArena. It captures the
> vision, the architecture, every completed stage, the data model, the runtime
> behavior, the decisions made and *why*, the known gaps, and the rules a future
> contributor must follow to **continue** the architecture rather than redesign it.
>
> **Status at handoff:** Stages 0–9 are complete and verified. Stage 9 (Knowledge
> Graph) is finished: background event-driven sync, bounded edge derivation,
> stale-edge removal, filtered graph-aware expansion, full integration tests, and
> a live-Neo4j suite (skipped when no server). **Test suite: `219 passing,
> 4 skipped`** (PyTest; the 4 skips are the live-Neo4j tests). The companion
> deep-dive lives in [`docs/architecture.md`](architecture.md) (sections §1–§15).

---

## 1. Project Vision

### What MemoryArena is
MemoryArena is a **production-grade memory backend for AI agents**. Agents and
applications send it raw signal — conversations, events, documents — and it
returns **structured, retrievable, self-evolving memory**:

- **Semantic memory** — facts/knowledge, stored as text + vector embeddings (pgvector).
- **Episodic memory** — time-stamped events, stored relationally (PostgreSQL).
- **Relational/graph memory** — entities and how they connect (Neo4j, Stage 9).

It is *not* a chatbot and *not* a RAG demo. It is the **memory layer** an agent
platform builds on: ingest → score → evolve → embed → retrieve → assemble context.

### Why it exists
LLM agents are stateless. Bolting a vector store onto a prompt ("basic RAG")
gives recall but no *memory*: no notion of which facts matter, which are stale,
which contradict, which reinforce each other, or how they relate. MemoryArena
treats memory as a first-class, evolving domain with its own lifecycle and
intelligence.

### Long-term goals
- A multi-tenant memory service that scales to **millions of users**.
- Memory that **self-evolves**: reinforced on use, decayed over time, promoted
  when valuable, archived when stale.
- **Hybrid retrieval** (semantic + lexical + intelligence + recency) plus
  **graph expansion**, feeding a **token-budgeted context package** ready for any LLM.
- A clean seam to add **LangGraph workflows**, an **agent runtime**, and a
  **dashboard** without reworking the core.

### How it differs from basic RAG
| Basic RAG | MemoryArena |
| --- | --- |
| Chunk → embed → top-k cosine → stuff prompt | Full memory lifecycle with scoring & evolution |
| All chunks equal | Memories have importance/utility/frequency/recency/confidence; promotion & priority |
| No staleness handling | Time-based **decay** + **archival** |
| Vector-only retrieval | **Hybrid fusion**: vector + BM25 + memory-score + recency, then **reranking** |
| No relationships | **Knowledge graph** of typed edges + **graph expansion** |
| Prompt = concatenation | **Context Assembly**: selection, **consolidation** (dedupe), **conflict detection**, **compression**, strict token budget |
| Framework-coupled | **Clean Architecture** — domain knows nothing of frameworks |

---

## 2. Architecture Overview

MemoryArena follows **Clean Architecture** (Ports & Adapters). The one rule that
governs everything: **source dependencies point inward only.** The domain is the
stable center and imports *nothing* from outer layers or third-party frameworks.

### Layers

- **Domain Layer** (`app/domain`) — Enterprise rules. Pure-Python entities
  (`Memory`, `MemoryScore`, `MemoryRelation`, `MemoryVersion`), value objects
  (enums), domain events, and domain exceptions. **Zero** framework imports.
- **Application Layer** (`app/application`) — Use cases, services, and **ports**
  (abstract interfaces) the use cases depend on: repositories, Unit of Work,
  event dispatcher, embedding provider, reranker, graph repository, token
  counter, compressor. DTOs are plain dataclasses. No HTTP, no SQL.
- **Persistence Layer** (`app/infrastructure/database`, `app/repositories`) —
  Async SQLAlchemy 2.x models, mappers (domain ↔ ORM), repository
  implementations, the SQLAlchemy Unit of Work, Alembic migrations.
- **API Layer** (`app/api`) — FastAPI routers, pydantic schemas (the wire
  contract), the composition root (`dependencies/providers.py`), middleware.
- **Event System** (`app/infrastructure/events`, dispatch wiring) — In-process
  domain event dispatcher; handlers translate memory events into side effects
  (embeddings, graph sync) **after commit**.
- **Memory Intelligence Layer** (`app/application/services` — intelligence,
  decay strategies, analytics) — Reinforcement, decay, promotion, archival.
- **Embedding Layer** (`app/infrastructure/embeddings`, embedding service) —
  Provider abstraction + implementations; event-driven generation/storage.
- **Retrieval Layer** (`app/application/services/retrieval`) — Vector + BM25
  retrievers, weighted fusion, reranking.
- **Context Assembly Layer** (`app/application/services/context`) — Selection,
  consolidation, conflict detection, compression → `ContextPackage`.
- **Knowledge Graph Layer** (`app/application/services/graph`,
  `app/infrastructure/graph`) — *(Stage 9, in progress)* graph repository
  (Neo4j / in-memory), relationship engine, traversal, graph-aware retrieval.

### Dependency flow (inward only)

```
            HTTP request
                │
                ▼
   API (FastAPI routers, pydantic schemas, providers = composition root)
                │   maps schema → DTO, injects concrete adapters
                ▼
   Application (use cases / services)  ── depend on ──▶  PORTS (interfaces)
                │                                            ▲
                ▼                                            │ implemented by
            Domain (entities, value objects, events)        │
                ▲                                            │
                └──────────── Infrastructure ────────────────┘
            (SQLAlchemy repos, pgvector, Redis, Neo4j, providers, dispatcher)

  Domain depends on nothing. Application depends on Domain + its own ports.
  Infrastructure & API depend inward. Nothing inward depends outward.
```

The **composition root** is `app/api/v1/dependencies/providers.py`: the single
place where abstract ports are bound to concrete adapters via FastAPI `Depends`.

---

## 3. Current Implementation Status

> Each stage's deep dive is in `docs/architecture.md`. Below: purpose,
> components, key decisions.

### Stage 0 — Architecture
- **Purpose:** Lock in a scalable monorepo + Clean Architecture skeleton before any logic.
- **Components:** `backend/`, `frontend/`, `infrastructure/`, `docs/`, `tests/`, `.github/`, `docker-compose.yml`, `.env.example`, ADRs.
- **Decisions:** Monorepo (version-locked contract + client + schema + infra); the dependency rule; three distinct "model" types (domain entity ≠ ORM model ≠ API schema).

### Stage 1 — Infrastructure
- **Purpose:** Runnable, observable FastAPI foundation.
- **Components:** App factory + lifespan (`main.py`), `core/config.py` (Pydantic Settings), `core/logging.py` (JSON logs + correlation IDs), `core/exceptions.py` (global handlers + standardized envelope), connection managers (`PostgresManager`, `RedisManager`, `Neo4jManager`), `/api/v1/health` + `/version`, DI providers.
- **Decisions:** Singleton connection managers (each owns a pool); `health_check()` never raises; fail-fast config validation; correlation IDs via `ContextVar`; composition root in `providers.py`.

### Stage 2 — Domain Model
- **Purpose:** The pure-Python "memory language."
- **Components:** `Memory` (aggregate root), `MemoryScore` (frozen VO), `MemoryRelation`, `MemoryVersion`; enums `MemoryType`/`MemoryStatus`/`RelationType`; domain events; `DomainError` hierarchy; unit tests.
- **Decisions:** Aggregate records events (`pull_events()`); score is immutable (evolution → new instance); status owns its transition table; versions are frozen snapshots; **no pydantic in domain**.

### Stage 3 — Persistence
- **Purpose:** Async persistence behind the Stage 2 ports.
- **Components:** SQLAlchemy `Base` + mixins + cross-dialect `Vector` type; 6 ORM models; mappers; `MemoryRepositoryImpl`/`MemoryRelationRepositoryImpl`/`MemoryVersionRepositoryImpl`; `SQLAlchemyUnitOfWork`; Alembic `0001_initial_schema`.
- **Decisions:** Repositories never commit (UoW owns the transaction); mappers are the only both-sides importers; soft deletion (`deleted_at`); enums stored as string values; pgvector schema reserved early.

### Stage 4 — Application + APIs
- **Purpose:** Use cases and HTTP endpoints for CRUD/search.
- **Components:** `CreateMemoryUseCaseImpl` / `Update` / `Delete` / `Search`; `MemoryService` (orchestration facade); pydantic schemas; `/api/v1/memories` (POST/GET/PUT/DELETE, POST `/search`, GET `/user/{id}`); the in-process event dispatcher; application exceptions mapped to HTTP.
- **Decisions:** Use cases own the transaction and dispatch events **after commit**; service is orchestration-only; three error tiers mapped centrally; pydantic only at the edge.

### Stage 5 — Memory Intelligence
- **Purpose:** Make memories evolve.
- **Components:** `MemoryIntelligenceService` (reinforce/decay/promote/archive/evaluate); `IntelligenceConfig`; `DecayStrategy` (Exponential/Linear); `MemoryAnalyticsService`; `priority` column (migration `0002`); endpoints `/memories/{id}/reinforce|promote|archive`, `/memories/analytics`; `Scheduler` port (interfaces only).
- **Decisions:** Reinforcement raises frequency+utility & refreshes recency; **decay does not touch `updated_at`** (so idle-based archival stays honest); promotion keeps status ACTIVE + bumps priority; pluggable decay strategy.

### Stage 6 — Embedding Pipeline
- **Purpose:** Generate/store embeddings, event-driven.
- **Components:** `EmbeddingProvider` port; `OpenAIEmbeddingProvider`, `LocalBGEEmbeddingProvider`, `DeterministicEmbeddingProvider`; `factory` (select by `EMBEDDING_PROVIDER`); `EmbeddingService`; `EmbeddingJobProcessor` port + `InProcessEmbeddingJobProcessor`; `EmbeddingEventHandler`; `dimensions` column (migration `0003`).
- **Decisions:** Fully event-driven (no direct calls); app-scoped service uses a **UoW factory** (fresh transaction per background job); upsert keyed on `(memory_id, model_name)` → idempotent; lazy SDK imports.

### Stage 7 — Hybrid Retrieval
- **Purpose:** Production-grade hybrid search.
- **Components:** `VectorRetriever` (cosine), `KeywordRetriever` (Okapi BM25), `HybridRetriever` (weighted fusion), `Reranker` port + `SimpleCrossEncoderReranker`, `MemoryRetrievalService`, `RetrievalConfig`; endpoints `/retrieval/search`, `/retrieval/debug`.
- **Decisions:** Vector + keyword run **concurrently** (each its own UoW); BM25 min-max normalized into the candidate union; memory-intelligence + recency as fusion signals; reranker behind a port.

### Stage 8 — Context Assembly
- **Purpose:** Turn retrieved memories into a token-budgeted context package.
- **Components:** `MemorySelectionService`, `ConflictDetector`, `MemoryConsolidationService`, `ContextCompressor` port + `HeuristicContextCompressor`, `ContextBuilderService`, `TokenCounter` port + `HeuristicTokenCounter`; endpoints `/context/build`, `/context/debug`.
- **Decisions:** Budget enforced at **selection** (promoted-first, greedy) and guaranteed at **compression**; consolidation keeps highest-scored duplicate; conflicts are *reported* not auto-resolved; no LLM compression yet.

### Stage 9 — Knowledge Graph *(complete)*
- **Purpose:** Graph memory + graph-aware retrieval.
- **Components:** `GraphRepository` port; `InMemoryGraphRepository` (offline default) + `Neo4jGraphRepository`; `GraphRelationshipService` (derives RELATED_TO/SUPPORTS/USED_IN); `GraphTraversalService`; `GraphSyncService` + `GraphEventHandler` driving an async `GraphJobProcessor` (`InProcessGraphJobProcessor`, drained on shutdown); `GraphAwareRetrievalService` (hybrid → filtered graph expansion with provenance tags); endpoints `/graph/search|traverse|memory/{id}|debug`.
- **Decisions:** graph sync runs **off the request path** via a background job processor (mirrors the embedding pipeline); edge derivation is **bounded** to the most recent `max_sync_candidates` memories (O(K), not O(N²)); every sync **re-derives** edges (stale edges removed first); expansion is filtered by an **edge-type allowlist** (excludes `CONTRADICTS`), **tenant** (user_id), and **status** (ACTIVE).
- **Tests:** unit (repo/relationship/traversal) + integration (sync, events, graph-aware retrieval, API) + live-Neo4j (skipped when no server).

---

## 4. Repository Structure

```
memory_project/
├── backend/
│   ├── app/
│   │   ├── main.py                     # App factory + lifespan (connects datastores, wires event handlers)
│   │   ├── api/v1/
│   │   │   ├── router.py               # Aggregates all v1 routers
│   │   │   ├── dependencies/providers.py   # COMPOSITION ROOT (ports → adapters)
│   │   │   ├── middleware/             # (request-context logging lives in core/logging)
│   │   │   └── routes/                 # health, memories, retrieval, context, graph
│   │   ├── application/                # USE CASES + SERVICES + PORTS (framework-free)
│   │   │   ├── dto/                     # plain-dataclass DTOs (memory, retrieval, context, embedding, graph, analytics)
│   │   │   ├── interfaces/             # PORTS: repositories, unit_of_work, event_dispatcher,
│   │   │   │                           #        embedding_provider, embedding_job_processor,
│   │   │   │                           #        reranker, token_counter, context_compressor,
│   │   │   │                           #        graph_repository, scheduler
│   │   │   ├── services/               # memory_service, intelligence, analytics, decay_strategies,
│   │   │   │   ├── context/            #   selection, consolidation, conflict_detector, compressor, builder
│   │   │   │   ├── retrieval/          #   vector, keyword(bm25), hybrid, reranker, scoring, service
│   │   │   │   └── graph/              #   relationship, traversal, sync, event_handler, graph_aware
│   │   │   ├── use_cases/              # memory_use_cases (ABCs) + _impl
│   │   │   ├── exceptions.py           # ApplicationError, MemoryNotFound/ValidationException
│   │   │   └── presenters.py           # domain → response DTO
│   │   ├── core/                       # config, logging (JSON + correlation IDs), exceptions (handlers)
│   │   ├── domain/                     # ★ PURE: entities, value_objects, events, exceptions
│   │   ├── infrastructure/             # FRAMEWORKS & DRIVERS (depend inward)
│   │   │   ├── database/               # base, session, mappers, unit_of_work, models/, postgres.py
│   │   │   ├── cache/redis.py          # RedisManager
│   │   │   ├── graph/                  # neo4j.py (manager), neo4j_graph_repository, in_memory_graph_repository, factory
│   │   │   ├── embeddings/             # deterministic/openai/bge providers, factory, in_process_processor
│   │   │   ├── events/in_process_dispatcher.py
│   │   │   └── llm/                    # graphs/, chains/  (placeholders for LangGraph — empty)
│   │   ├── repositories/               # concrete repo impls (memory, relation, version, embedding)
│   │   └── schemas/                    # pydantic wire schemas (responses, memory, retrieval, context, graph, analytics)
│   ├── alembic/                        # env.py, script.py.mako, versions/ (0001,0002,0003)
│   ├── tests/                          # unit/, integration/, e2e/ (asyncio.run pattern; sqlite/aiosqlite)
│   ├── pyproject.toml                  # deps + ruff/black/isort/mypy/pytest config
│   └── alembic.ini
├── frontend/                           # Next.js 15 scaffold (Stage 0; not yet built)
├── infrastructure/                     # docker/, k8s/, monitoring/, scripts/ (k8s & monitoring are placeholders)
├── docs/                               # architecture.md, project_state.md (this file), adr/
├── docker-compose.yml                  # postgres(+pgvector), redis, neo4j, backend
└── .env.example
```

**Major folders.** `domain/` is the untouchable core. `application/interfaces/`
holds the ports — the seams that make everything swappable. `application/services/`
holds orchestration grouped by capability (context/retrieval/graph). `repositories/`
+ `infrastructure/` are the adapters. `api/v1/dependencies/providers.py` is where
it's all wired together.

---

## 5. Domain Model

All under `app/domain`, pure Python (stdlib only).

### Entities

- **`Memory`** (`entities/memory.py`) — the **aggregate root**. Fields: `id`,
  `user_id`, `content`, `memory_type`, `status`, `score` (a `MemoryScore`),
  `metadata`, `version`, `is_promoted`, `priority`, `created_at`, `updated_at`,
  and a private `_events` buffer. Behavior methods enforce invariants and record
  events: `create()` (factory), `update_content()`, `reinforce()`, `decay()`,
  `promote()`, `archive()`, `restore()`, `delete()`, `rollback_to(version)`.
  Callers retrieve recorded events via `pull_events()` after the unit of work commits.
- **`MemoryScore`** (`entities/memory_score.py`) — frozen value object with five
  normalized [0,1] components: `importance`, `utility`, `frequency`, `recency`,
  `confidence`. `calculate_total_score()` returns the weighted sum.
  `reinforced()` and `decayed()` return **new** instances. Weights are `ClassVar`s.
- **`MemoryRelation`** (`entities/memory_relation.py`) — a typed, directed,
  weighted edge between two memories (`source_memory_id`, `target_memory_id`,
  `relation_type`, `weight`, `metadata`). Rejects self-edges.
- **`MemoryVersion`** (`entities/memory_version.py`) — frozen snapshot
  (`memory_id`, `version_number`, `content`, `memory_type`, `status`, `metadata`,
  `reason`). `capture(memory)` deep-copies mutable metadata so history is immutable.

### Enums (value objects)

- **`MemoryType`**: `FACT`, `GOAL`, `PREFERENCE`, `SKILL`, `PROJECT`, `EXPERIENCE`.
- **`MemoryStatus`**: `ACTIVE`, `ARCHIVED`, `DELETED` — owns `can_transition_to()`.
  Allowed: `ACTIVE→{ARCHIVED,DELETED}`, `ARCHIVED→{ACTIVE,DELETED}`, `DELETED→∅`.
- **`RelationType`**: `RELATED_TO`, `DEPENDS_ON`, `DERIVED_FROM`, `REINFORCES`, `CONTRADICTS`.

### Domain Events (`events/memory_events.py`)

Frozen, `kw_only` dataclasses extending `DomainEvent` (carries `event_id`,
`occurred_at`):

- **`MemoryCreated`** — memory_id, user_id, memory_type.
- **`MemoryUpdated`** — memory_id, user_id, version, reason.
- **`MemoryArchived`** — memory_id, user_id.
- **`MemoryDeleted`** — memory_id, user_id.
- **`MemoryPromoted`** — memory_id, user_id, total_score, priority.
- **`MemoryReinforced`** — memory_id, user_id, frequency, utility, total_score.
- **`MemoryDecayed`** — memory_id, user_id, recency, total_score.

### Lifecycle

```
Created → (Scored) → Linked → Reinforced ⇄ Promoted ⇄ Decayed → Archived → Deleted
```
- **Created**: `Memory.create()` → `MemoryCreated`, status ACTIVE, version 1, priority 0.
- **Scored**: `total_score = calculate_total_score()` (computed, not a state).
- **Linked**: `MemoryRelation` edges / graph edges.
- **Reinforced**: `reinforce()` raises frequency+utility, recency→1.0, refreshes `updated_at` → `MemoryReinforced`.
- **Promoted**: `promote()` (needs ACTIVE + score ≥ threshold) sets `is_promoted`, `priority += 1` → `MemoryPromoted`.
- **Decayed**: `decay(factor)` multiplies recency, **does not** touch `updated_at` → `MemoryDecayed`.
- **Archived**: `archive()` ACTIVE→ARCHIVED → `MemoryArchived` (`restore()` reverses).
- **Deleted**: `delete()` → DELETED (terminal); persisted as a soft-delete tombstone.

Illegal transitions raise `InvalidMemoryStateError`; empty content raises
`MemoryValidationError`; bad score components raise `InvalidScoreError`.

---

## 6. Database Schema

PostgreSQL via async SQLAlchemy 2.x. Constraint naming convention is set on
`Base.metadata` for stable Alembic output. All tables have `created_at`/`updated_at`;
`users` and `memories` add `deleted_at` (soft delete).

### Tables

- **`users`** — `id` (UUID PK), `email` (unique), `display_name`, timestamps, `deleted_at`.
- **`memories`** — `id` (UUID PK), `user_id` (FK→users, CASCADE), `content` (Text),
  `memory_type` (str), `status` (str), `version` (int), `is_promoted` (bool),
  `priority` (int, added in `0002`), `meta` (JSONB; the domain's `metadata`),
  timestamps, `deleted_at`. Indexes: `user_id`, composite `(user_id, status)`, `memory_type`.
- **`memory_scores`** — `id` (PK), `memory_id` (FK→memories, CASCADE, **unique** → 1:1),
  `importance`/`utility`/`frequency`/`recency`/`confidence` (Float), timestamps.
- **`memory_relations`** — `id` (PK), `source_memory_id`/`target_memory_id`
  (FK→memories), `relation_type` (str), `weight` (Float), `meta` (JSONB),
  unique `(source, target, relation_type)`, indexes on source & target.
- **`memory_versions`** — `id` (PK), `memory_id` (FK), `version_number` (int),
  `content`, `memory_type`, `status`, `meta`, `reason`, unique `(memory_id, version_number)`.
- **`memory_embeddings`** — `embedding_id` (PK), `memory_id` (FK), `vector`
  (pgvector `vector(1536)`), `model_name` (str), `dimensions` (int, added in `0003`),
  timestamps, unique `(memory_id, model_name)`, index on `memory_id`.

### Relationships
`users 1─N memories`; `memories 1─1 memory_scores`; `memories 1─N memory_versions`;
`memories 1─N memory_embeddings`; `memories N─N memories` via `memory_relations`.
All child FKs are `ON DELETE CASCADE` for hard-delete integrity (the app uses
soft delete by default).

### pgvector usage
The `vector` column is `pgvector.sqlalchemy.Vector(1536)` on PostgreSQL. A custom
`Vector` **TypeDecorator** (`infrastructure/database/base.py`) degrades to a
JSON-encoded `TEXT` on other dialects (SQLite in tests), so the **entire schema is
creatable on any dialect**. Migration `0001` runs `CREATE EXTENSION IF NOT EXISTS
vector`. Stage 6 populates embeddings; Stage 7 reads them for cosine similarity.
At large scale, `MemoryEmbeddingRepository.list_candidates` is the seam to push
similarity into a pgvector ANN index (`ORDER BY embedding <=> :q`).

---

## 7. Event Architecture

### Event dispatcher
`InProcessEventDispatcher` (`infrastructure/events/in_process_dispatcher.py`)
implements the `EventDispatcher` port. Handlers are matched along the event's
**MRO**, so registering on the base `DomainEvent` is a catch-all. Handler failures
are **isolated and logged** — one bad subscriber never breaks the request or
starves the others. A module-level singleton `in_process_dispatcher` is shared
process-wide; a default audit-logging handler is registered on `DomainEvent`.

### Post-commit dispatch pattern
The aggregate records events as side effects of behavior into `_events`. The
**use case dispatches them only after `uow.commit()` succeeds**:

```
async with uow:
    ... mutate aggregate ...
    await uow.commit()
await dispatcher.dispatch(memory.pull_events())   # only durable changes emit events
```

This guarantees events reflect **persisted** state — a rolled-back change never
emits an event.

### Embedding event handlers
`EmbeddingEventHandler` subscribes to `MemoryCreated`/`MemoryUpdated` → submit an
**UPSERT** job, and `MemoryDeleted` → **DELETE** job, to the
`InProcessEmbeddingJobProcessor` (asyncio background tasks, with `drain()` for
shutdown/tests). The job loads the memory, generates the embedding, and upserts
it — off the request's critical path.

### Graph event handlers *(Stage 9)*
`GraphEventHandler` subscribes to the same events and calls `GraphSyncService` to
upsert/remove the memory's graph node and derive edges.

### Why events
Events decouple producers (use cases) from consumers (embeddings, graph, future
analytics/outbox). Adding a side effect = registering a handler; no use-case edits.
The handler registration happens in `main.py`'s **lifespan** (after datastores
connect), keeping the wiring explicit and the dispatcher swappable for a real
broker (Kafka/RabbitMQ) later.

---

## 8. Memory Intelligence Engine

`MemoryIntelligenceService` (`application/services/memory_intelligence_service.py`)
evolves memories. Each operation runs in a UoW, mutates the aggregate (which
records the event), commits, then dispatches.

### Operations
- **Reinforcement** (`reinforce_memory`) — successful reuse: frequency +`step`,
  utility +`step` (each capped at 1.0), recency→1.0, refresh `updated_at` → `MemoryReinforced`.
- **Decay** (`decay_memory`) — recency × factor from an injected `DecayStrategy`;
  **does not** refresh `updated_at` → `MemoryDecayed`.
- **Promotion** (`promote_memory`) — requires ACTIVE + `total_score ≥ threshold`;
  sets `is_promoted`, `priority += 1` → `MemoryPromoted` (else `InvalidMemoryStateError` → HTTP 409).
- **Archival** (`archive_memory`) — eligible when `total_score < archival_score_threshold`
  **AND** idle ≥ `archival_max_idle_days`; `force=True` overrides → `MemoryArchived`.
- **Evaluate** (`evaluate_memory`) — returns total_score, is_promotable, should_archive.

### Scoring formula
```
total_score = 0.30·importance + 0.25·utility + 0.20·frequency + 0.15·recency + 0.10·confidence
```
Weights sum to 1.0 and inputs are in [0,1], so the total is guaranteed normalized.

### Thresholds (`IntelligenceConfig`)
- `reinforcement_step = 0.10`
- `promotion_threshold = 0.65`
- `archival_score_threshold = 0.30`, `archival_max_idle_days = 30`

### Decay strategies
`ExponentialDecayStrategy(half_life_days=7)` (default; `0.5^(age/half_life)`) and
`LinearDecayStrategy(rate_per_day)`. Age is measured from `updated_at`.

### Analytics
`MemoryAnalyticsService.get_analytics(user_id?)` returns `total/active/archived/
promoted` counts, `average_score`, and a `score_distribution` (5 buckets), computed
in Python over non-deleted memories. Endpoint: `GET /api/v1/memories/analytics`.

### Scheduler (ports only)
`application/interfaces/scheduler.py` defines `Scheduler`, `ScheduledJob`, and
abstract `DecaySweepJob`/`ArchivalSweepJob`/`PromotionSweepJob` for a future
background runner (APScheduler/Celery/K8s CronJob) — **no implementation yet**.

---

## 9. Embedding Pipeline

### Provider abstraction
`EmbeddingProvider` port: `embed_text`, `embed_batch`, `model_name`, `dimensions`,
`health_check`. Selected by `EMBEDDING_PROVIDER` via `infrastructure/embeddings/factory.py`
(cached singleton).

- **`OpenAIEmbeddingProvider`** (`openai`) — OpenAI embeddings; client lazily
  imported/injectable; `health_check` from config (API key present). 1536-dim.
- **`LocalBGEEmbeddingProvider`** (`bge`) — local sentence-transformers BGE;
  model lazily loaded/injectable; native dims (384–1024).
- **`DeterministicEmbeddingProvider`** (`hash`, **default**) — reproducible,
  offline, dependency-free hash vectors; used in dev/tests so the pipeline runs
  without keys or downloads.

### Lifecycle
Event-driven: `MemoryCreated`/`Updated` → upsert, `MemoryDeleted` → delete.
`EmbeddingService` (app-scoped, takes a **UoW factory**) runs each job in its own
transaction. Storage is keyed `(memory_id, model_name)` → **upsert** (idempotent
re-embedding). `MemoryEmbeddingRepositoryImpl` provides `save/get/update/delete/list_candidates`.

### Model migration strategy
Each row records `model_name` + `dimensions` + `created_at`, so vectors are
attributable to the exact model. Migration is additive and zero-downtime:
1. add a column/index for the new dimensionality (pgvector columns are fixed-width);
2. dual-write (point provider at the new model; new memories embed under the new `model_name`);
3. backfill via a background job (re-embed via the same UPSERT path);
4. cut reads over to the new `model_name`; drop the old rows/column.
Embeddings are derived data — always regenerable from `Memory.content`.

---

## 10. Hybrid Retrieval Engine

`MemoryRetrievalService` orchestrates: **query → vector candidates → keyword
candidates → fusion → reranking → results**.

- **Vector retrieval** (`VectorRetriever`) — embeds the query, fetches candidate
  embeddings (`list_candidates`, filtered to the provider's `model_name`),
  ranks by **cosine similarity** (clamped to [0,1]).
- **BM25 retrieval** (`KeywordRetriever`) — Okapi BM25 over `content` + metadata
  values; returns only positively-matching docs; `k1=1.5`, `b=0.75`.
- **Fusion** (`HybridRetriever`) — runs vector + keyword **concurrently**, unions
  by memory id, normalizes BM25 (min-max across the union), and blends.
- **Reranking** (`SimpleCrossEncoderReranker` behind the `Reranker` port) —
  multiplies the fused score by `(1 + overlap_weight · lexical_overlap)` and re-sorts.

### Retrieval scoring formula
```
final = w_vector·vector + w_bm25·bm25 + w_memory·memory + w_recency·recency
      = 0.50·vector + 0.20·bm25 + 0.20·memory + 0.10·recency     (defaults)
```
- `vector` = cosine, clamped [0,1].
- `bm25` = Okapi BM25, min-max normalized across the candidate union.
- `memory` = `(0.4·importance + 0.3·utility + 0.3·frequency)` + promotion bonus
  (+0.15) + priority bonus (≤0.10), clamped [0,1]. **This is where Memory
  Intelligence boosts ranking.**
- `recency` = `0.5^(age_days/half_life)` (default half-life 30 days), over `updated_at`.

### Weighting strategy
Semantic similarity leads (it generalizes beyond exact words); lexical matching
anchors exact terms/IDs; memory and recency are tie-breakers that let high-value
or fresh memories win close calls. All weights live in `RetrievalConfig` and are
injected → tunable per environment/tenant. Endpoints: `/retrieval/search`,
`/retrieval/debug` (full per-signal breakdown).

---

## 11. Context Assembly Engine

`ContextBuilderService` runs: **retrieval → selection → consolidation → conflict
detection → compression → ContextPackage**.

- **Selection** (`MemorySelectionService`) — orders candidates **promoted-first,
  then by score**, and greedily admits them while they fit the token budget;
  overflow dropped (`reason="token_budget"`). Greedy-by-priority lets a small
  lower-ranked memory use leftover budget.
- **Consolidation** (`MemoryConsolidationService`) — near-duplicates (token
  Jaccard ≥ 0.85) collapse to the **highest-scored** representative; recorded in a
  `ConsolidationRecord`; losers dropped (`reason="duplicate"`).
- **Conflict detection** (`ConflictDetector`) — flags `negation_contradiction`
  when two memories share significant terms (stopwords + negation markers removed)
  but exactly one is negated (e.g. "I use Python" vs "I no longer use Python").
  Conflicts are **reported, not auto-resolved**.
- **Compression** (`HeuristicContextCompressor` behind `ContextCompressor`) —
  (1) whitespace normalization (lossless), (2) prune lowest-scored memories if
  still over budget (`reason="compression"`), (3) render `- (type) content` lines.
  Reports `original_tokens`/`compressed_tokens`/`ratio`/`removed_memories`.

### Token budgeting
Estimated by `HeuristicTokenCounter` (~4 chars/token) behind the `TokenCounter`
port (tiktoken-swappable). The budget is enforced **twice**: at selection (primary
gate) and at compression (final guarantee) — so the emitted package is **always**
within `max_tokens`.

### `ContextPackage`
`query`, `user_id`, `memories: list[ContextMemory]`, `context_text` (the assembled
string), `total_tokens`, `max_tokens`, `metadata`. The debug variant
(`ContextDebugPackage`) adds selected, dropped (with reasons), conflicts,
consolidations, and compression stats. Endpoints: `/context/build`, `/context/debug`.

---

## 12. Testing Strategy

- **Current count: `201 passing`** (PyTest). 0 failures.
- **Runner pattern:** async code is driven by `asyncio.run()` inside ordinary
  test functions, so **no `pytest-asyncio` plugin** is required.
- **Isolated DB:** integration tests use **in-memory SQLite** (`aiosqlite` +
  `StaticPool`); the cross-dialect `Vector` type lets the full schema (incl.
  `memory_embeddings`) be created. API tests use FastAPI `TestClient` with
  **dependency overrides** (no lifespan, no real datastores).

### Coverage areas
- **Unit:** config validation, domain entity transitions/events, score math,
  mappers, event dispatcher, memory evolution, decay strategies, scheduler ports,
  BM25, retrieval scoring, reranker, token counter, selection, conflict detection,
  consolidation, compression, embedding providers, embedding job processor,
  in-memory graph repo, graph relationship & traversal.
- **Integration:** repositories + UoW, use cases, embedding repo/service/events,
  vector/keyword/hybrid retrievers, retrieval service, context builder,
  analytics, memory intelligence, migration structure, and the API surfaces
  (memories, intelligence, retrieval, context).
- **Helpers:** `tests/integration/_db.py` (engine + seed user),
  `tests/integration/_retrieval.py` (seed + embed memories).

### Expectations going forward
Every new capability ships with unit tests for its pure logic and integration
tests against SQLite (or a fake service for API). Keep the suite green; do not
regress the count.

---

## 13. Architecture Decisions

1. **Clean Architecture + the dependency rule.** Business logic is the expensive,
   slow-to-change asset; frameworks/DBs/LLMs are commodities we will swap. Keeping
   the domain framework-free means we can replace any outer layer without touching
   the core and unit-test the core with zero infrastructure.
2. **Three model types kept separate** (domain entity ≠ ORM model ≠ API schema).
   Each evolves for its own reasons; mappers/presenters translate.
3. **Repository pattern + ports.** Use cases depend on abstract repositories, never
   on SQLAlchemy. This is the seam for read-replicas/sharding/alternate stores.
4. **Unit of Work owns the transaction.** Repositories never commit; multi-entity
   operations (e.g. snapshot a version *and* update a memory) are atomic.
5. **Event-driven side effects.** Embeddings and graph sync are decoupled from use
   cases via domain events; producers only record events. Enables an outbox/broker later.
6. **Post-commit dispatch.** Events fire only after durable success.
7. **Self-evolving memory (intelligence as a first-class layer).** Importance/
   utility/frequency/recency/confidence + promotion/priority + decay/archival —
   this is what makes it memory, not storage.
8. **Hybrid retrieval over vector-only.** Semantic + lexical + intelligence +
   recency, fused with configurable weights, then reranked behind a port.
9. **Context assembly before any LLM.** Selection + consolidation + conflict
   detection + compression produce a deterministic, budgeted `ContextPackage`.
   The platform is useful and testable with **no LLM in the loop**.
10. **Offline-first defaults** (`hash` embeddings, `memory` graph backend, SQLite
    tests) so the whole pipeline runs without external services or API keys.
11. **Config-driven, injected strategies** (decay, retrieval weights, providers,
    graph backend) — tunable per environment/tenant without code changes.

---

## 14. Known Limitations

- **Knowledge graph (Stage 9) is complete** — background event-driven sync,
  bounded edge derivation, stale-edge removal, filtered graph-aware expansion,
  unit + integration tests, and a live-Neo4j suite (skipped when no server) all
  in place. Default backend remains in-memory (offline-first); the Neo4j path is
  exercised by the live suite when a server is available.
- **No LangGraph workflows** — `infrastructure/llm/{graphs,chains}` are empty placeholders.
- **No LLM-based context compression** — only the heuristic compressor; `LLMCompressor` is a future port impl.
- **No agent runtime / chat generation / RAG response** — by design; out of scope so far.
- **No background scheduler implementation** — only the `Scheduler` ports; decay/archival/promotion sweeps are manual/API-triggered.
- **Vector search is brute-force** in the repository (exact cosine over candidates) — correct but not ANN-scaled; the `list_candidates` port is the seam for a pgvector ANN index.
- **No observability stack** — JSON logs + correlation IDs exist; no metrics/tracing/dashboards (LangSmith/OTel) yet.
- **No authn/authz enforcement** — `user_id` is passed in; JWT settings exist but no auth middleware.
- **Frontend not built** — Next.js scaffold only.
- **In-memory graph + dispatcher are process-local** — not multi-instance safe until backed by Neo4j / a real broker.
- **Analytics & BM25 load candidates into memory** — fine at moderate scale; SQL/index pushdown is a future optimization.

---

## 15. Future Roadmap

Recommended order (each builds on the seams already in place):

- **Stage 9 — Knowledge Graph Layer (Neo4j).** *Finish what's started.* Complete
  graph integration/API tests, verify `Neo4jGraphRepository` against a live server,
  and document graph expansion. **Why first:** the ports, services, and event sync
  already exist; closing this unlocks graph-aware retrieval as a first-class feature.
- **Stage 10 — LangGraph Agent Runtime.** Build extraction/consolidation workflows
  in `infrastructure/llm/graphs`. **Why next:** retrieval + context + graph are the
  inputs an agent runtime consumes; the `ContextPackage` is its natural interface.
- **Stage 11 — Advanced Memory Workflows.** LLM-assisted conflict resolution,
  summarization-based `LLMCompressor`, automatic relationship inference, scheduled
  decay/archival sweeps (implement the `Scheduler` ports). **Why:** these need both
  the graph (Stage 9) and the agent runtime (Stage 10).
- **Stage 12 — Next.js Dashboard.** Visualize memories, scores, the graph, and
  retrieval/context debug output. **Why after the engine:** the API contract is
  stable and the `/debug` endpoints already expose everything a UI needs.
- **Stage 13 — LangSmith + Observability.** Tracing for LLM/graph workflows,
  metrics, dashboards, alerts. **Why now:** there are finally LLM workflows worth
  tracing, and a UI to surface health.
- **Stage 14 — Production Hardening.** AuthN/AuthZ, rate limiting, multi-tenant
  isolation, pgvector ANN indexing, read replicas, real broker for events, k8s +
  monitoring manifests. **Why last:** harden once the feature surface is stable.

The order moves **inputs → workflows → surfacing → operations**: each stage's
prerequisites are satisfied by the prior ones, and nothing requires reworking the core.

---

## 16. Instructions For Future Claude Sessions

**Continue the architecture; do not redesign it.**

### What should NOT be changed
- The **dependency rule**. Never make `domain/` import from `application/`,
  `infrastructure/`, `api/`, or any third-party framework. Never make
  `application/` import FastAPI/SQLAlchemy/Neo4j/Redis/pydantic.
- The **three model types** stay separate (domain entity, ORM model, API schema).
- **Repositories never commit**; the **Unit of Work** owns transactions.
- **Events dispatch after commit**, via the dispatcher — don't call embeddings/graph
  services directly from use cases.
- **Pydantic stays at the API edge** (`schemas/`). DTOs and domain are plain dataclasses/stdlib.
- Existing **public API contracts** (`/api/v1/...`, the `APIResponse` envelope,
  correlation-id header) — extend, don't break; version with `v2` if needed.

### Architectural constraints
- New capabilities are added as **services behind ports** in `application/`, with
  concrete adapters in `infrastructure/`, wired in `api/v1/dependencies/providers.py`
  (the composition root). Don't instantiate infrastructure inside use cases/services.
- Cross-cutting side effects = **new event handlers**, registered in `main.py` lifespan.
- Keep **offline-first defaults** working (hash embeddings, in-memory graph, SQLite
  tests) so the suite runs without external services.
- Configuration goes through **Pydantic Settings** (`core/config.py`) and injected
  config dataclasses — no magic constants in logic.
- Schema changes go through **Alembic migrations** (next is `0004`); never edit a
  live schema by hand. Keep the cross-dialect `Vector` type working.

### Dependency rules (quick check before importing)
- `domain` → (stdlib only).
- `application` → `domain` + its own `interfaces`/`dto` (+ pure helpers). No frameworks.
- `infrastructure` / `repositories` → may import `application` ports + `domain` + drivers.
- `api` → may import everything inward (it's the composition root + delivery).

### Coding standards
- Python 3.12, full type hints, `from __future__ import annotations`.
- Async I/O end-to-end (async SQLAlchemy, async drivers).
- Tooling configured in `pyproject.toml`: **Ruff** (lint, line length 100), **Black**,
  **isort** (black profile), **mypy** (strict). Match surrounding style and docstring density.
- Module docstrings explain *why a component exists*, not just what it does.

### Testing expectations
- Keep the suite **green** (currently **201 passing**) and never regress the count.
- New pure logic → **unit tests**; new I/O → **integration tests** against SQLite
  (use `tests/integration/_db.py` / `_retrieval.py`); new endpoints → **API tests**
  with dependency overrides + fakes.
- Use the **`asyncio.run()`** pattern (no `pytest-asyncio` dependency). Use
  `aiosqlite` + `StaticPool` for in-memory DBs.
- Run: `cd backend && PYTHONPATH=. python -m pytest tests -q`.

### Environment notes
- Local dev/tests default to fully offline providers. Real datastores come up via
  `docker compose up` (postgres+pgvector, redis, neo4j, backend).
- `.env.example` is the template; **never commit real secrets** (a real OpenAI key
  was once pasted into `.env.example` and removed — keep it placeholder-only).
- `cp .env.example .env`, set a real `JWT_SECRET` (≥16 chars, not "change-me"),
  then `cd backend && alembic upgrade head` for a real database.

---

*End of handoff. For per-stage depth (diagrams, formulas, rationale, test
breakdowns), see [`docs/architecture.md`](architecture.md).*
