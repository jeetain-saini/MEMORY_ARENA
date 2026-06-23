# Stage 18 — Large-Tenant Scalability Benchmark

Reproduce:

```bash
cd backend
PYTHONPATH=. python scripts/benchmark_stage18.py \
  --sizes 2000,4000,10000,50000,100000 --bruteforce-cap 4000
```

Pure in-memory compute (no DB/graph servers) so the numbers isolate the
algorithmic scaling of the two Stage 18 hotspots. Synthetic memories are grouped
into topics (~50 memories per topic) so token overlap — and the resulting cluster
structure — is realistic rather than degenerate. Deterministic (`seed=1234`).
Absolute timings are machine-dependent; the **shape of the curve** and the
**relative speedups** are the point.

## 18.2 — Clustering connected-components

Inverted-index candidate generation (Stage 18.2) vs the pre-18.2 exhaustive
O(n²) all-pairs Jaccard scan. The exhaustive scan is only run up to the
brute-force cap (4,000) — it is quadratic and would take **hours** at 100k.

| N | clusters | inverted-index | brute-force O(n²) | speedup |
|--:|--:|--:|--:|--:|
| 2,000 | 40 | 520 ms | 4,846 ms | 9.3× |
| 4,000 | 80 | 2,167 ms | 30,226 ms | 13.9× |
| 10,000 | 200 | 6,202 ms | n/a (capped) | — |
| 50,000 | 1,000 | 30,692 ms | n/a (capped) | — |
| 100,000 | 2,000 | 61,269 ms | n/a (capped) | — |

The brute-force scan is quadratic: it grows ~7.5× (4,846→30,226 ms) for a 2×
size increase. Extrapolating from the 4,000-memory point, an O(n²) scan at
100,000 memories would take on the order of **5+ hours**; the inverted index
completes the same tenant in **~61 seconds**. The inverted-index path itself
scales near-linearly here because topic count grows with N (postings lists stay
bounded), which is the realistic regime.

## 18.1 — GraphSnapshot batched degree lookups

Building the batched adjacency index once and serving N degree lookups
(Stage 18.1) vs the pre-18.1 shape where each memory linearly scans the full
edge list (what a per-memory `get_edges` devolves to without an index, O(N·E)).
The naive scan is capped at 4,000.

| N | edges | batched (build + N lookups) | per-memory scan | speedup |
|--:|--:|--:|--:|--:|
| 2,000 | 2,999 | 4.4 ms | 844 ms | 190× |
| 4,000 | 5,998 | 11.0 ms | 3,449 ms | 313× |
| 10,000 | 15,000 | 28.9 ms | n/a (capped) | — |
| 50,000 | 75,000 | 293 ms | n/a (capped) | — |
| 100,000 | 150,000 | 912 ms | n/a (capped) | — |

The batched index is linear in nodes+edges: 100,000 memories with 150,000 edges
indexes and answers all degree lookups in **under one second**, versus the
quadratic per-memory scan whose speedup is already 313× at only 4,000 memories.
This is the per-pass win the maintenance cycle gets for free now that importance
evolution and forgetting read degree/isolation from the snapshot instead of one
`get_edges` round-trip per memory.

## Takeaways

- **18.1** turns the per-pass graph access from O(N) round-trips (each O(E) in
  the worst case) into a single batched read plus O(1) lookups — sub-second at
  100k.
- **18.2** turns clustering from quadratic to near-linear on realistic data,
  making 100k-memory tenants tractable (~1 min) where they were previously
  hours.
- **18.3 / 18.4** then make that cycle safe and faster across tenants: a
  distributed lock guarantees a single owner, and bounded parallelism overlaps
  per-tenant I/O up to the connection-pool ceiling.
