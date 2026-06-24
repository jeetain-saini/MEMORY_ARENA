"use client";

import { useQuery } from "@tanstack/react-query";

import { getMemory } from "@/services/memories";

export function useMemory(memoryId: string | null) {
  return useQuery({
    queryKey: ["memory", memoryId],
    queryFn: ({ signal }) => getMemory(memoryId as string, signal),
    enabled: !!memoryId,
  });
}
