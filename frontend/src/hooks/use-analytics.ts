"use client";

import { useQuery } from "@tanstack/react-query";

import { getAnalytics } from "@/services/analytics";

export function useAnalytics(userId: string) {
  return useQuery({
    queryKey: ["analytics", userId],
    queryFn: ({ signal }) => getAnalytics(userId, signal),
    enabled: userId.length > 0,
  });
}
