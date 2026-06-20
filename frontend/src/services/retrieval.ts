import { apiRequest } from "@/lib/api-client";
import type { RetrievalResult, RetrievalSearchRequest } from "@/types/retrieval";

export function retrievalSearch(request: RetrievalSearchRequest): Promise<RetrievalResult> {
  return apiRequest<RetrievalResult>("/retrieval/search", { method: "POST", body: request });
}

export function retrievalDebug(request: RetrievalSearchRequest): Promise<RetrievalResult> {
  return apiRequest<RetrievalResult>("/retrieval/debug", { method: "POST", body: request });
}
