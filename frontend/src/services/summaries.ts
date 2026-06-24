import { apiRequest } from "@/lib/api-client";
import type { MemorySummary } from "@/types/summary";

// NOTE: Stage 11 stores summaries but exposes NO read endpoint. This client
// targets the endpoint the dashboard expects once it is added
// (GET /api/v1/summaries/{user_id}); until then the hook surfaces a graceful
// "not available" state. No backend changes were made in Stage 12.
export function listSummaries(userId: string, signal?: AbortSignal): Promise<MemorySummary[]> {
  return apiRequest<MemorySummary[]>(`/summaries/${userId}`, { signal });
}
