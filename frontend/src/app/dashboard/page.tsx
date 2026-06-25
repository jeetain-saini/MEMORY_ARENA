"use client";

import { Bot, Database, Layers, Share2 } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { AnimatedNumber } from "@/components/shared/animated-number";
import { DistributionBars } from "@/components/shared/distribution-bars";
import { MemoryCard } from "@/components/shared/memory-card";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { EmptyState, ErrorState, LoadingRows, NoUserState } from "@/components/shared/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useGraphOverview } from "@/hooks/use-graph";
import { useUserMemories } from "@/hooks/use-memories";
import { useSummaries } from "@/hooks/use-summaries";
import { deriveMemoryEvents } from "@/lib/memory-events";
import { cn, formatDateTime, formatScore } from "@/lib/utils";
import { MEMORY_TYPES } from "@/types/api";

function HealthTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="text-gradient text-2xl font-semibold tabular-nums">
        <AnimatedNumber value={value} />
      </div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export default function DashboardPage() {
  const { userId, ready, hasUser } = useCurrentUser();
  const analytics = useAnalytics(userId);
  // Backend caps the list endpoint at limit<=100 (Query(le=100)); 100 is the max.
  const memories = useUserMemories(userId, 100);
  const summaries = useSummaries(userId);
  const graph = useGraphOverview(userId || null);

  const all = useMemo(() => memories.data ?? [], [memories.data]);

  const recentEvents = useMemo(
    () => deriveMemoryEvents(all, summaries.data ?? []).slice(0, 8),
    [all, summaries.data],
  );
  const categories = useMemo(() => {
    const counts = MEMORY_TYPES.map((t) => ({
      type: t,
      count: all.filter((m) => m.memory_type === t).length,
    }));
    const max = Math.max(1, ...counts.map((c) => c.count));
    return { counts, max };
  }, [all]);
  const important = useMemo(
    () => [...all].sort((a, b) => b.total_score - a.total_score).slice(0, 5),
    [all],
  );
  const topRetrieved = useMemo(
    () =>
      [...all]
        .filter((m) => (m.retrieval_count ?? 0) > 0)
        .sort((a, b) => (b.retrieval_count ?? 0) - (a.retrieval_count ?? 0))
        .slice(0, 5),
    [all],
  );
  const superseded = useMemo(() => all.filter((m) => m.status === "superseded").length, [all]);

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Memory health, knowledge categories, and recent activity at a glance."
      />

      {/* Quick actions */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { href: "/memories", label: "Explore Memories", Icon: Database },
          { href: "/graph", label: "Knowledge Graph", Icon: Share2 },
          { href: "/agent", label: "Ask the Agent", Icon: Bot },
          { href: "/context", label: "Assemble Context", Icon: Layers },
        ].map(({ href, label, Icon }) => (
          <Link
            key={href}
            href={href}
            className="lift group flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.035] p-4 backdrop-blur-xl"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500/20 to-violet-500/20 text-indigo-300 transition-colors group-hover:text-indigo-200">
              <Icon className="h-4 w-4" />
            </span>
            <span className="text-sm font-medium text-foreground">{label}</span>
          </Link>
        ))}
      </div>

      {/* Headline stats */}
      {analytics.isError ? (
        <ErrorState error={analytics.error} />
      ) : analytics.isLoading || !analytics.data ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <LoadingRows key={i} rows={1} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard title="Total memories" value={analytics.data.total_memories} />
          <StatCard title="Active" value={analytics.data.active_memories} />
          <StatCard title="Promoted" value={analytics.data.promoted_memories} />
          <StatCard
            title="Average score"
            value={formatScore(analytics.data.average_score)}
            hint={`${analytics.data.archived_memories} archived`}
          />
        </div>
      )}

      {/* Memory health + knowledge categories */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Memory health</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <HealthTile label="Active" value={analytics.data?.active_memories ?? 0} />
              <HealthTile label="Archived" value={analytics.data?.archived_memories ?? 0} />
              <HealthTile label="Superseded" value={superseded} />
              <HealthTile label="Promoted" value={analytics.data?.promoted_memories ?? 0} />
              <HealthTile label="Summaries" value={summaries.data?.length ?? 0} />
              <HealthTile label="Graph nodes" value={graph.data?.nodes.length ?? 0} />
              <HealthTile label="Relationships" value={graph.data?.edges.length ?? 0} />
              <HealthTile label="Total" value={analytics.data?.total_memories ?? 0} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Knowledge categories</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {memories.isLoading ? (
              <LoadingRows rows={3} />
            ) : (
              categories.counts.map(({ type, count }) => (
                <div key={type}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="capitalize text-muted-foreground">{type}</span>
                    <span className="tabular-nums text-foreground">{count}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
                      style={{ width: `${(count / categories.max) * 100}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Most important + top retrieved */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Most important memories</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {memories.isLoading ? (
              <LoadingRows rows={2} />
            ) : important.length === 0 ? (
              <EmptyState title="No memories yet" />
            ) : (
              important.map((m) => <MemoryCard key={m.id} memory={m} />)
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top retrieved memories</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {memories.isLoading ? (
              <LoadingRows rows={2} />
            ) : topRetrieved.length === 0 ? (
              <EmptyState
                title="No retrievals yet"
                description="Ask the agent a question to start using memories."
              />
            ) : (
              topRetrieved.map((m) => (
                <MemoryCard
                  key={m.id}
                  memory={m}
                  footer={
                    <p className="text-xs text-muted-foreground">
                      retrieved {m.retrieval_count ?? 0}×
                    </p>
                  }
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent activity + score distribution */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Recent activity</CardTitle>
          </CardHeader>
          <CardContent>
            {memories.isLoading ? (
              <LoadingRows rows={3} />
            ) : recentEvents.length === 0 ? (
              <EmptyState title="No activity yet" />
            ) : (
              <ol className="space-y-2">
                {recentEvents.map((e) => (
                  <li
                    key={e.id}
                    className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2"
                  >
                    <span
                      className={cn(
                        "h-1.5 w-1.5 shrink-0 rounded-full",
                        e.kind === "created"
                          ? "bg-emerald-400"
                          : e.kind === "superseded"
                            ? "bg-violet-400"
                            : e.kind === "archived"
                              ? "bg-zinc-400"
                              : e.kind === "summary"
                                ? "bg-indigo-400"
                                : "bg-sky-400",
                      )}
                    />
                    <span className="text-sm text-foreground">{e.title}</span>
                    <span className="truncate text-xs text-muted-foreground">{e.detail}</span>
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                      {formatDateTime(e.at)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Score distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {analytics.data ? (
              <DistributionBars data={analytics.data.score_distribution} />
            ) : (
              <LoadingRows rows={2} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
