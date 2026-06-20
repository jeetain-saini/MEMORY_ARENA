"use client";

import { useQuery } from "@tanstack/react-query";

import { listSummaries } from "@/services/summaries";

export function useSummaries(userId: string) {
  return useQuery({
    queryKey: ["summaries", userId],
    queryFn: () => listSummaries(userId),
    enabled: userId.length > 0,
    retry: false, // the endpoint may not exist yet → fail fast to the empty state
  });
}
