"use client";

import { useQuery } from "@tanstack/react-query";

import { getGraphMemory, getGraphOverview, graphTraverse } from "@/services/graph";

export function useGraphMemory(memoryId: string | null) {
  return useQuery({
    queryKey: ["graph", "memory", memoryId],
    queryFn: ({ signal }) => getGraphMemory(memoryId as string, signal),
    enabled: !!memoryId,
  });
}

export function useGraphOverview(userId: string | null) {
  return useQuery({
    queryKey: ["graph", "overview", userId],
    queryFn: ({ signal }) => getGraphOverview(userId as string, signal),
    enabled: !!userId,
  });
}

export function useGraphTraversal(nodeId: string | null, depth: number) {
  return useQuery({
    queryKey: ["graph", "traverse", nodeId, depth],
    queryFn: ({ signal }) => graphTraverse(nodeId as string, depth, signal),
    enabled: !!nodeId,
  });
}
