"use client";

import { ArrowRightLeft, GitBranch, Layers, Sparkles, TrendingUp, type LucideIcon } from "lucide-react";

import { MemoryEvolution } from "@/components/memory/memory-evolution";
import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { useGraphMemory } from "@/hooks/use-graph";
import { useSummaries } from "@/hooks/use-summaries";
import { EDGE_STYLES } from "@/lib/constants";
import { formatDateTime, formatScore } from "@/lib/utils";
import type { GraphEdgeType } from "@/types/api";
import type { GraphEdge, GraphNode } from "@/types/graph";
import type { Memory } from "@/types/memory";

// Edge types that represent "this replaced / derives from that" lineage.
const LINEAGE: ReadonlySet<GraphEdgeType> = new Set<GraphEdgeType>([
  "contradicts",
  "supersedes",
  "promoted_from",
  "derived_from",
]);

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-2.5">
      <div className="text-gradient text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </h4>
      {children}
    </div>
  );
}

export function MemoryInsights({ memory, userId }: { memory: Memory; userId: string }) {
  const graph = useGraphMemory(memory.id);
  const summaries = useSummaries(userId);

  const edges = graph.data?.edges ?? [];
  const neighbors = graph.data?.neighbors ?? [];
  const rels: { node: GraphNode; edge: GraphEdge }[] = [];
  for (const e of edges) {
    const otherId = e.source_id === memory.id ? e.target_id : e.source_id;
    const node = neighbors.find((n) => n.node_id === otherId);
    if (node) rels.push({ node, edge: e });
  }
  const lineage = rels.filter((r) => LINEAGE.has(r.edge.edge_type));
  const membership = (summaries.data ?? []).filter((s) =>
    s.source_memory_ids.includes(memory.id),
  );

  const evidence = memory.metadata?.evidence;

  return (
    <div className="space-y-5">
      {/* Memory evolution (Phase D) — real evidence history, or empty state */}
      <Section icon={TrendingUp} title="Memory evolution">
        {evidence ? (
          <MemoryEvolution evidence={evidence} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No evidence history yet — this memory hasn&apos;t been reinforced across conversations.
          </p>
        )}
      </Section>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        <Tile label="Relevance" value={formatScore(memory.total_score)} />
        <Tile label="Retrieved" value={memory.retrieval_count ?? 0} />
        <Tile label="Version" value={memory.version} />
        <Tile label="Priority" value={memory.priority} />
        <Tile label="Promoted" value={memory.is_promoted ? "Yes" : "No"} />
      </div>

      {/* Why retrieved — explainability */}
      <Section icon={Sparkles} title="Why is this memory retrieved?">
        <p className="text-sm leading-relaxed text-foreground/85">
          Ranked by a weighted blend of <strong>importance</strong>, <strong>utility</strong>,{" "}
          <strong>frequency</strong>, and <strong>recency</strong> — its composite relevance score
          is <span className="tabular-nums">{formatScore(memory.total_score)}</span>. It has been
          retrieved <span className="tabular-nums">{memory.retrieval_count ?? 0}</span> time(s)
          {memory.is_promoted
            ? ", and is promoted, which adds a ranking boost so it surfaces ahead of peers."
            : "; repeated retrieval raises its importance over time."}
        </p>
      </Section>

      {/* Lifecycle */}
      <Section icon={Layers} title="Lifecycle">
        <ol className="space-y-1.5 text-sm">
          <li className="flex gap-2">
            <span className="text-emerald-600">Created</span>
            <span className="text-muted-foreground">{formatDateTime(memory.created_at)}</span>
          </li>
          {memory.updated_at !== memory.created_at ? (
            <li className="flex gap-2">
              <span className="text-sky-600">Updated</span>
              <span className="text-muted-foreground">{formatDateTime(memory.updated_at)}</span>
            </li>
          ) : null}
          {memory.is_promoted ? (
            <li className="flex gap-2">
              <span className="text-amber-600">Promoted</span>
              <span className="text-muted-foreground">recurring / high-value memory</span>
            </li>
          ) : null}
          {memory.status === "archived" ? (
            <li className="flex gap-2">
              <span className="text-zinc-600">Archived</span>
              <span className="text-muted-foreground">
                superseded by a newer contradictory memory; kept for history, hidden from retrieval
              </span>
            </li>
          ) : null}
          {memory.status === "superseded" ? (
            <li className="flex gap-2">
              <span className="text-violet-600">Superseded</span>
              <span className="text-muted-foreground">replaced by a newer memory</span>
            </li>
          ) : null}
          {memory.status === "forgotten" ? (
            <li className="flex gap-2">
              <span className="text-orange-600">Forgotten</span>
              <span className="text-muted-foreground">aged out: old, low-value, rarely used</span>
            </li>
          ) : null}
        </ol>
      </Section>

      {/* Contradiction & lineage */}
      <Section icon={ArrowRightLeft} title="Contradiction & lineage">
        {graph.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading graph relationships…</p>
        ) : lineage.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No recorded contradictions or supersession links for this memory.
          </p>
        ) : (
          <ul className="space-y-2">
            {lineage.map((r) => {
              const style = EDGE_STYLES[r.edge.edge_type];
              return (
                <li
                  key={`${r.edge.source_id}:${r.edge.target_id}:${r.edge.edge_type}`}
                  className="rounded-lg border border-border bg-card p-2.5 text-sm"
                >
                  <span
                    className="mr-2 text-xs font-medium uppercase tracking-wide"
                    style={{ color: style.color }}
                  >
                    {style.label}
                  </span>
                  <span className="text-foreground/90">{r.node.label}</span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {/* Related memories / graph nodes */}
      <Section icon={GitBranch} title="Related memories & graph nodes">
        {graph.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : rels.length === 0 ? (
          <p className="text-sm text-muted-foreground">No graph-connected memories yet.</p>
        ) : (
          <ul className="space-y-2">
            {rels.slice(0, 8).map((r) => {
              const style = EDGE_STYLES[r.edge.edge_type];
              return (
                <li
                  key={`${r.edge.source_id}:${r.edge.target_id}:${r.edge.edge_type}`}
                  className="flex items-center gap-2 rounded-lg border border-border bg-card p-2.5 text-sm"
                >
                  <span
                    className="shrink-0 rounded-full px-2 py-0.5 text-[11px]"
                    style={{ color: style.color, backgroundColor: `${style.color}22` }}
                  >
                    {style.label}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-foreground/90">{r.node.label}</span>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      {/* Summary membership */}
      <Section icon={Layers} title="Summary membership">
        {summaries.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : membership.length === 0 ? (
          <p className="text-sm text-muted-foreground">Not part of any rolling summary yet.</p>
        ) : (
          <ul className="space-y-2">
            {membership.map((s) => (
              <li
                key={s.id}
                className="rounded-lg border border-border bg-card p-2.5 text-sm"
              >
                <div className="mb-1 flex items-center gap-2">
                  <MemoryTypeBadge type={s.scope} />
                  <span className="text-xs text-muted-foreground">
                    {s.source_count} source{s.source_count === 1 ? "" : "s"}
                  </span>
                </div>
                <p className="line-clamp-2 text-foreground/85">{s.summary_text}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
