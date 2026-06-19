# MemoryArena

> A production-grade, multi-tenant **AI Memory System** — built to give LLM agents durable, queryable, and graph-aware long-term memory at scale.

MemoryArena ingests conversations and events, distills them into structured **memories** (semantic, episodic, procedural), and serves them back to agents through fast semantic search (pgvector), relationship-aware retrieval (Neo4j knowledge graph), and low-latency caching (Redis). Memory extraction and consolidation are orchestrated as **LangGraph** stateful workflows.

This repository is a **monorepo** organized around **Clean Architecture** so that business rules stay independent of frameworks, databases, and delivery mechanisms — the prerequisite for evolving any one component without rewriting the system.

---

## Project Status — Stage 0 (Foundation)

This commit contains **structure only**: the directory layout, architecture documentation, and infrastructure scaffolding. **No business logic has been implemented yet.** Every Python package is a placeholder, and service modules document their intended responsibility without behavior.

The goal of Stage 0 is to lock in an architecture that can scale to **millions of users** before a single use case is written.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| **Backend** | Python 3.12, FastAPI, LangGraph, LangChain, SQLAlchemy, Alembic |
| **Datastores** | PostgreSQL + pgvector (semantic), Neo4j (graph), Redis (cache / queues) |
| **Frontend** | Next.js 15 (App Router), TypeScript, TailwindCSS, shadcn/ui |
| **Infrastructure** | Docker, Docker Compose, GitHub Actions (CI/CD) |

---

## Top-Level Layout

```
memory_project/
├── backend/          # FastAPI service — Clean Architecture (domain → application → infrastructure → api)
├── frontend/         # Next.js 15 dashboard & playground (App Router)
├── infrastructure/   # Dockerfiles, container configs, k8s manifests, ops scripts
├── docs/             # Architecture docs, ADRs, diagrams
├── tests/            # System-level tests spanning services (e2e, contract, load)
├── .github/          # GitHub Actions CI/CD workflows
├── docker-compose.yml
├── .env.example
└── README.md
```

> Why a monorepo? A single repository keeps the API contract, the client that consumes it, the database schema, and the infra that runs them **version-locked together**. One pull request can change a domain entity, its persistence, its API schema, and the frontend type that mirrors it — reviewed and shipped atomically. See [`docs/architecture.md`](docs/architecture.md) for the full rationale.

---

## Getting Started (Stage 0)

Stage 0 brings the infrastructure online; application containers will start serving traffic once Stage 1 adds entrypoints.

```bash
# 1. Copy environment template and fill in secrets
cp .env.example .env

# 2. Bring up the backing services (Postgres+pgvector, Neo4j, Redis)
docker compose up -d postgres neo4j redis

# 3. (Stage 1+) Start the application services
# docker compose up backend frontend
```

---

## Documentation

- **[docs/architecture.md](docs/architecture.md)** — Full architecture: Clean Architecture layering, dependency rule, data model, request lifecycle, scaling strategy, and a folder-by-folder rationale.
- **docs/adr/** — Architecture Decision Records (one file per significant decision).

---

## Roadmap

| Stage | Scope |
| --- | --- |
| **0** | Foundation — structure, architecture, infra scaffolding *(this commit)* |
| **1** | Domain entities, core config, app entrypoints, health checks |
| **2** | Memory ingestion use cases + LangGraph extraction workflow |
| **3** | Semantic (pgvector) + graph (Neo4j) retrieval |
| **4** | Frontend dashboard & memory playground |
| **5** | Observability, rate limiting, multi-tenant hardening |

---

## License

TBD.
