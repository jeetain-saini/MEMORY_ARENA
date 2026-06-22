import { apiRequest } from "@/lib/api-client";
import type {
  GraphAwareResult,
  GraphMemoryView,
  GraphOverview,
  GraphSearchRequest,
  GraphTraversalResult,
} from "@/types/graph";

export function getGraphMemory(memoryId: string): Promise<GraphMemoryView> {
  return apiRequest<GraphMemoryView>(`/graph/memory/${memoryId}`);
}

export function getGraphOverview(userId: string): Promise<GraphOverview> {
  return apiRequest<GraphOverview>(`/graph/overview/${userId}`);
}

export function graphTraverse(nodeId: string, depth: number): Promise<GraphTraversalResult> {
  return apiRequest<GraphTraversalResult>("/graph/traverse", {
    method: "POST",
    body: { node_id: nodeId, depth },
  });
}

export function graphSearch(request: GraphSearchRequest): Promise<GraphAwareResult> {
  return apiRequest<GraphAwareResult>("/graph/search", { method: "POST", body: request });
}
