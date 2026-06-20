# MemoryArena Dashboard (Stage 12)

A Next.js 15 frontend for exploring, querying, and inspecting MemoryArena. It is
**frontend-only** — it consumes the existing API and contains no business logic.

## Stack

- Next.js 15 (App Router) · React 19 · TypeScript (strict)
- Tailwind CSS + shadcn/ui (new-york)
- TanStack Query (server state)
- React Flow (`@xyflow/react`) + dagre (graph visualization)

## Features

| Route | Feature | API |
| --- | --- | --- |
| `/` | Dashboard — counts, promoted, score distribution, recent activity | `GET /memories/analytics`, `GET /memories/user/{id}` |
| `/memories` | Memory Explorer — search, type/status filters, detail + actions | `POST /memories/search`, `GET /memories/{id}`, reinforce/promote/archive/delete |
| `/graph` | Graph Explorer — inferred & CONTRADICTS edges, dependency chains | `POST /graph/traverse`, `GET /graph/memory/{id}` |
| `/context` | Context Playground — retrieval, context package, compression | `POST /retrieval/debug`, `POST /context/debug` |
| `/agent` | Agent Playground — streaming answer, citations, execution trace | `POST /query/stream` (SSE), `POST /query` |
| `/summaries` | Summary Explorer — project/goal/experience summaries | `GET /summaries/{id}` *(endpoint not yet exposed — see note)* |

> **Summary Explorer:** Stage 11 stores summaries but exposes no read endpoint.
> The page degrades gracefully and will populate automatically once a thin
> `GET /api/v1/summaries/{user_id}` endpoint is added — no frontend change needed.

## Getting started

```bash
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_BASE_URL (and optional default user)
npm install
npm run dev                        # http://localhost:3000
```

The backend must be running (default `http://localhost:8000`). CORS already
allows `http://localhost:3000`.

### Environment

- `NEXT_PUBLIC_API_BASE_URL` — API base, e.g. `http://localhost:8000/api/v1`.
- `NEXT_PUBLIC_DEFAULT_USER_ID` — tenant the dashboard loads with.

**User identity (no auth):** the active `user_id` resolves in priority order —
(1) `localStorage` override, (2) `NEXT_PUBLIC_DEFAULT_USER_ID`, (3) an
empty-state prompt. It is editable in the top bar and persisted to
`localStorage`, then injected into every request via `UserContext` /
`useCurrentUser()`.

## Scripts

- `npm run dev` — dev server
- `npm run build` — production build
- `npm run typecheck` — `tsc --noEmit` (strict)
- `npm run lint` — Next.js ESLint

## Architecture

- `services/*` — typed API clients (one per API group) over a single
  envelope-unwrapping `lib/api-client`.
- `hooks/*` — TanStack Query hooks; `use-agent-stream` reads the SSE POST stream
  via `fetch` + a `ReadableStream` reader (`lib/sse`) with `AbortController`
  cancellation.
- `components/ui` — shadcn primitives; `components/{shared,graph,context,agent,memory}`
  — reusable, feature-grouped components.
- `providers/*` — `QueryProvider` + `UserProvider`.
