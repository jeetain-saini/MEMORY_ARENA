# Observability (Phase 4)

MemoryArena records counters and latency aggregates in-process on the hot path
(the `MetricsSink` port) and exposes them three ways:

- **JSON** — `GET /api/v1/observability/metrics` (human/debug).
- **Prometheus** — `GET /api/v1/observability/prometheus` (scrape target).
- **Traces** — `GET /api/v1/observability/traces` (recent `/query` runs).

## Prometheus

`render_prometheus` converts the snapshot to text exposition: counters become
`counter` series, latencies expand to `avg`/`0.5`/`0.95` quantile gauges plus a
`_count`. Names are sanitized and namespaced under `memoryarena_`
(e.g. `cache.hit.analytics` → `memoryarena_cache_hit_analytics`,
`retrieval.latency_ms` → `memoryarena_retrieval_latency_ms{quantile="0.95"}`).

Config in `infrastructure/monitoring/`:
- `prometheus.yml` — scrape job hitting `/api/v1/observability/prometheus`.
- `alert.rules.yml` — alerts: backend down, retrieval/vector p95 latency, low
  cache hit ratio, maintenance lock contention, forgetting spikes.
- `grafana_dashboard.json` — import with a Prometheus datasource.

```bash
# Run Prometheus + Grafana against a local backend:
docker run -p 9090:9090 -v $PWD/infrastructure/monitoring:/etc/prometheus prom/prometheus
docker run -p 3001:3000 grafana/grafana   # import grafana_dashboard.json
```

## What is measured

| Area | Example metrics |
|---|---|
| Cache (4.7) | `memoryarena_cache_hit_analytics`, `memoryarena_cache_miss_analytics` |
| Retrieval / DB (4.6) | `memoryarena_retrieval_latency_ms`, `memoryarena_vector_latency_ms` |
| Maintenance job (4.4) | `memoryarena_intelligence_maintenance_skipped_total` |
| Intelligence engine (4.5) | `memoryarena_memories_{promoted,forgotten,clustered,importance_evolved}_total`, `memoryarena_clustering_pair_comparisons_total` |

Because the exposition renders *whatever the sink has recorded*, any metric added
via `MetricsSink.incr/observe` appears automatically — no endpoint changes.

> Note: the scrape endpoint is under `/api/v1`; with `AUTH_ENABLED=true` allow
> the Prometheus scraper (e.g. an allowlisted IP or a scrape token) or expose it
> on an internal-only listener.
