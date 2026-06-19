# ADR 0001 — Record Architecture Decisions

- **Status:** Accepted
- **Date:** 2026-06-19

## Context

MemoryArena is designed to scale to millions of users and will evolve across
many stages and contributors. Decisions about layering, data stores, and
boundaries need a durable, reviewable record so future engineers understand
*why* the system is shaped the way it is — not just *what* it does.

## Decision

We will use **Architecture Decision Records (ADRs)**. Each significant
architectural decision gets a numbered Markdown file in `docs/adr/`, using the
format: Context → Decision → Consequences. ADRs are immutable once accepted;
a reversal is captured in a new ADR that supersedes the old one.

## Consequences

- **+** Decision history is explicit, searchable, and lives with the code.
- **+** Onboarding and reviews are faster; rationale is not lost to turnover.
- **−** A small, deliberate authoring cost per significant decision.

## Related

The foundational decisions (Clean Architecture, the dependency rule, the
monorepo, and the pgvector + Neo4j + Redis split) are documented in
[`../architecture.md`](../architecture.md) and will be promoted into dedicated
ADRs as they are revisited.
