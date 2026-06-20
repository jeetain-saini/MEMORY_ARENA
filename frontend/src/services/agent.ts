import { apiRequest, apiStream } from "@/lib/api-client";
import type { QueryResponse } from "@/types/agent";

export function queryAgent(userId: string, query: string): Promise<QueryResponse> {
  return apiRequest<QueryResponse>("/query", {
    method: "POST",
    body: { user_id: userId, query },
  });
}

export function queryAgentStream(
  userId: string,
  query: string,
  signal?: AbortSignal,
): Promise<Response> {
  return apiStream("/query/stream", { user_id: userId, query }, signal);
}
