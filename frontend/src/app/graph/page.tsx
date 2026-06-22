"use client";

import { Suspense, useMemo, useState } from "react";

import { EdgeLegend } from "@/components/graph/edge-legend";
import { GraphCanvas } from "@/components/graph/graph-canvas";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState, LoadingRows, NoUserState } from "@/components/shared/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useGraphOverview } from "@/hooks/use-graph";
import { useResolveContradiction } from "@/hooks/use-memory-actions";
import { EDGE_STYLES } from "@/lib/constants";
import type { GraphEdgeType } from "@/types/api";
import type { GraphEdge, GraphNode } from "@/types/graph";

function GraphExplorer() {
  const { userId, ready, hasUser } = useCurrentUser();
  const overview = useGraphOverview(userId);
  const resolve = useResolveContradiction(userId ?? "");

  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);

  const nodeById = useMemo(() => {
    const map = new Map<string, GraphNode>();
    overview.data?.nodes.forEach((n) => map.set(n.node_id, n));
    return map;
  }, [overview.data]);

  const presentTypes = useMemo(() => {
    const set = new Set<GraphEdgeType>();
    overview.data?.edges.forEach((e) => set.add(e.edge_type));
    return set;
  }, [overview.data]);

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  const node = selectedNode ? nodeById.get(selectedNode) : null;
  const label = (id: string) =>
    String(nodeById.get(id)?.properties.content ?? nodeById.get(id)?.label ?? id);

  return (
    <div>
      <PageHeader
        title="Graph Explorer"
        description="The full knowledge graph: RELATED_TO, CONTRADICTS, and SUPERSEDES edges."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-3">
          {overview.isError ? (
            <ErrorState error={overview.error} />
          ) : overview.isLoading ? (
            <LoadingRows rows={6} />
          ) : (overview.data?.nodes.length ?? 0) === 0 ? (
            <EmptyState
              title="No graph yet"
              description="No graph nodes for this tenant. Graph sync runs after memories are created."
            />
          ) : (
            <>
              <EdgeLegend present={presentTypes} />
              <GraphCanvas
                nodes={overview.data!.nodes}
                edges={overview.data!.edges}
                rootId={selectedNode}
                onNodeClick={(id) => {
                  setSelectedNode(id);
                  setSelectedEdge(null);
                }}
                onEdgeClick={(edge) => {
                  setSelectedEdge(edge);
                  setSelectedNode(null);
                }}
              />
              <div className="text-xs text-muted-foreground">
                {overview.data!.node_count} nodes · {overview.data!.edge_count} edges
              </div>
            </>
          )}
        </div>

        <div className="space-y-4">
          {/* Node details */}
          {node ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Memory node</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <p className="line-clamp-4">{label(node.node_id)}</p>
                <Detail k="Type" v={String(node.properties.memory_type ?? node.node_type)} />
                <Detail k="Status" v={String(node.properties.status ?? "—")} />
                <Detail k="Importance" v={fmt(node.properties.importance)} />
                <Detail k="Confidence" v={fmt(node.properties.confidence)} />
                <Detail k="Node id" v={node.node_id} mono />
              </CardContent>
            </Card>
          ) : null}

          {/* Edge details + contradiction resolution */}
          {selectedEdge ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">Relationship</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <span
                  className="inline-block rounded-md border px-2 py-1"
                  style={{ borderColor: EDGE_STYLES[selectedEdge.edge_type].color }}
                >
                  {EDGE_STYLES[selectedEdge.edge_type].label}
                </span>
                <Detail k="Source" v={label(selectedEdge.source_id)} />
                <Detail k="Target" v={label(selectedEdge.target_id)} />
                {selectedEdge.edge_type === "contradicts" ? (
                  <div className="space-y-2 pt-2">
                    <p className="text-muted-foreground">
                      Resolve: keep one memory, archive the other (a SUPERSEDES edge is recorded).
                    </p>
                    <div className="flex flex-col gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={resolve.isPending}
                        onClick={() =>
                          resolve.mutate({
                            keepId: selectedEdge.source_id,
                            archiveId: selectedEdge.target_id,
                          })
                        }
                      >
                        Keep source, archive target
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={resolve.isPending}
                        onClick={() =>
                          resolve.mutate({
                            keepId: selectedEdge.target_id,
                            archiveId: selectedEdge.source_id,
                          })
                        }
                      >
                        Keep target, archive source
                      </Button>
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {!node && !selectedEdge ? (
            <Card>
              <CardContent className="p-4 text-xs text-muted-foreground">
                Click a node for memory details, or an edge for relationship details. CONTRADICTS
                edges can be resolved here.
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function fmt(value: unknown): string {
  return typeof value === "number" ? value.toFixed(2) : "—";
}

function Detail({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-muted-foreground">{k}</span>
      <span className={mono ? "font-mono" : ""}>{v}</span>
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
