import { apiRequest } from "@/lib/api-client";
import type {
  GraphAwareResult,
  GraphMemoryView,
  GraphOverview,
  GraphSearchRequest,
  GraphTraversalResult,
} from "@/types/graph";

export function getGraphMemory(memoryId: string, signal?: AbortSignal): Promise<GraphMemoryView> {
  return apiRequest<GraphMemoryView>(`/graph/memory/${memoryId}`, { signal });
}

export function getGraphOverview(userId: string, signal?: AbortSignal): Promise<GraphOverview> {
  return apiRequest<GraphOverview>(`/graph/overview/${userId}`, { signal });
}

export function graphTraverse(
  nodeId: string,
  depth: number,
  signal?: AbortSignal,
): Promise<GraphTraversalResult> {
  return apiRequest<GraphTraversalResult>("/graph/traverse", {
    method: "POST",
    body: { node_id: nodeId, depth },
    signal,
  });
}

export function graphSearch(request: GraphSearchRequest): Promise<GraphAwareResult> {
  return apiRequest<GraphAwareResult>("/graph/search", { method: "POST", body: request });
}
