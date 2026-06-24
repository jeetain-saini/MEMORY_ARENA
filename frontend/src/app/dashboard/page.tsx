"use client";

import { useMemo } from "react";

import { DistributionBars } from "@/components/shared/distribution-bars";
import { MemoryCard } from "@/components/shared/memory-card";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { EmptyState, ErrorState, LoadingRows, NoUserState } from "@/components/shared/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalytics } from "@/hooks/use-analytics";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useUserMemories } from "@/hooks/use-memories";
import { formatScore } from "@/lib/utils";

export default function DashboardPage() {
  const { userId, ready, hasUser } = useCurrentUser();
  const analytics = useAnalytics(userId);
  const memories = useUserMemories(userId);

  const recent = useMemo(
    () =>
      [...(memories.data ?? [])]
        .sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at))
        .slice(0, 5),
    [memories.data],
  );
  const promoted = useMemo(
    () => (memories.data ?? []).filter((m) => m.is_promoted).slice(0, 5),
    [memories.data],
  );

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  return (
    <div>
      <PageHeader title="Dashboard" description="Memory counts, value, and recent activity." />

      {analytics.isError ? (
        <ErrorState error={analytics.error} />
      ) : analytics.isLoading || !analytics.data ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <LoadingRows rows={1} />
          <LoadingRows rows={1} />
          <LoadingRows rows={1} />
          <LoadingRows rows={1} />
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

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-1">
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

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Promoted memories</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {memories.isLoading ? (
              <LoadingRows rows={2} />
            ) : promoted.length === 0 ? (
              <EmptyState title="No promoted memories yet" />
            ) : (
              promoted.map((m) => <MemoryCard key={m.id} memory={m} />)
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Recent activity</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {memories.isLoading ? (
            <LoadingRows rows={3} />
          ) : recent.length === 0 ? (
            <EmptyState title="No memories for this user yet" />
          ) : (
            recent.map((m) => <MemoryCard key={m.id} memory={m} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}
