"use client";

import { useQuery } from "@tanstack/react-query";

import { getGraphMemory, graphTraverse } from "@/services/graph";

export function useGraphMemory(memoryId: string | null) {
  return useQuery({
    queryKey: ["graph", "memory", memoryId],
    queryFn: () => getGraphMemory(memoryId as string),
    enabled: !!memoryId,
  });
}

export function useGraphTraversal(nodeId: string | null, depth: number) {
  return useQuery({
    queryKey: ["graph", "traverse", nodeId, depth],
    queryFn: () => graphTraverse(nodeId as string, depth),
    enabled: !!nodeId,
  });
}
