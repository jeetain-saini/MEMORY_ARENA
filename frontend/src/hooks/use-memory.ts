"use client";

import { useQuery } from "@tanstack/react-query";

import { getMemory } from "@/services/memories";

export function useMemory(memoryId: string | null) {
  return useQuery({
    queryKey: ["memory", memoryId],
    queryFn: () => getMemory(memoryId as string),
    enabled: !!memoryId,
  });
}
