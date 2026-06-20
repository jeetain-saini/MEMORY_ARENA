"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EdgeLegend } from "@/components/graph/edge-legend";
import { GraphCanvas } from "@/components/graph/graph-canvas";
import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState, LoadingRows, NoUserState } from "@/components/shared/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useGraphTraversal } from "@/hooks/use-graph";
import { useUserMemories } from "@/hooks/use-memories";
import { EDGE_STYLES } from "@/lib/constants";
import type { GraphEdgeType } from "@/types/api";

function GraphExplorer() {
  const { userId, ready, hasUser } = useCurrentUser();
  const params = useSearchParams();
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [depth, setDepth] = useState(2);

  useEffect(() => {
    const fromUrl = params.get("memory");
    if (fromUrl) setNodeId(fromUrl);
  }, [params]);

  const memories = useUserMemories(userId, 25);
  const graph = useGraphTraversal(nodeId, depth);

  const presentTypes = useMemo(() => {
    const set = new Set<GraphEdgeType>();
    graph.data?.edges.forEach((e) => set.add(e.edge_type));
    return set;
  }, [graph.data]);

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  return (
    <div>
      <PageHeader
        title="Graph Explorer"
        description="Inferred relationships, CONTRADICTS edges, and dependency chains."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[18rem_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Root memory</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                placeholder="Memory id (UUID)"
                value={nodeId ?? ""}
                onChange={(e) => setNodeId(e.target.value || null)}
                className="font-mono text-xs"
              />
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                Depth
                <input
                  type="range"
                  min={1}
                  max={4}
                  value={depth}
                  onChange={(e) => setDepth(Number(e.target.value))}
                  className="flex-1"
                />
                <span className="w-4 tabular-nums">{depth}</span>
              </label>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Pick a memory</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-[18rem]">
                <div className="space-y-1 p-3">
                  {(memories.data ?? []).map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setNodeId(m.id)}
                      className="flex w-full flex-col items-start gap-1 rounded-md border p-2 text-left text-xs transition-colors hover:border-primary/40"
                    >
                      <MemoryTypeBadge type={m.memory_type} />
                      <span className="line-clamp-2">{m.content}</span>
                    </button>
                  ))}
                  {memories.data?.length === 0 ? (
                    <p className="p-2 text-xs text-muted-foreground">No memories.</p>
                  ) : null}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-3">
          {!nodeId ? (
            <EmptyState
              title="Select a memory"
              description="Pick a memory on the left (or paste a memory id) to render its relationship graph."
            />
          ) : graph.isError ? (
            <ErrorState error={graph.error} />
          ) : graph.isLoading ? (
            <LoadingRows rows={6} />
          ) : (graph.data?.nodes.length ?? 0) === 0 ? (
            <EmptyState
              title="No graph node yet"
              description="This memory has no graph node/edges. Graph sync and relationship inference run after ingestion."
            />
          ) : (
            <>
              <EdgeLegend present={presentTypes} />
              <GraphCanvas
                nodes={graph.data!.nodes}
                edges={graph.data!.edges}
                rootId={graph.data!.root_id}
                onNodeClick={setNodeId}
              />
              <EdgeBreakdown edges={graph.data!.edges} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function EdgeBreakdown({ edges }: { edges: { edge_type: GraphEdgeType }[] }) {
  const counts = edges.reduce<Record<string, number>>((acc, e) => {
    acc[e.edge_type] = (acc[e.edge_type] ?? 0) + 1;
    return acc;
  }, {});
  const keys = Object.keys(counts) as GraphEdgeType[];
  if (keys.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {keys.map((t) => (
        <span
          key={t}
          className="rounded-md border px-2 py-1 text-xs"
          style={{ borderColor: EDGE_STYLES[t].color }}
        >
          {EDGE_STYLES[t].label}: <strong>{counts[t]}</strong>
        </span>
      ))}
    </div>
  );
}

export default function GraphPage() {
  return (
    <Suspense fallback={<LoadingRows rows={4} />}>
      <GraphExplorer />
    </Suspense>
  );
}
