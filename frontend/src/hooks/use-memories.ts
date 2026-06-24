"use client";

import { useQuery } from "@tanstack/react-query";

import { listUserMemories, searchMemories } from "@/services/memories";
import type { MemorySearchRequest } from "@/types/memory";

export function useUserMemories(userId: string, limit = 50) {
  return useQuery({
    queryKey: ["memories", "list", userId, limit],
    queryFn: ({ signal }) => listUserMemories(userId, { limit }, signal),
    enabled: userId.length > 0,
  });
}

export function useMemorySearch(request: MemorySearchRequest, enabled: boolean) {
  return useQuery({
    queryKey: ["memories", "search", request],
    queryFn: ({ signal }) => searchMemories(request, signal),
    enabled: enabled && request.user_id.length > 0,
  });
}
