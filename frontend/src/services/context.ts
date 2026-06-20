import { apiRequest } from "@/lib/api-client";
import type { ContextDebug, ContextPackage, ContextRequest } from "@/types/context";

export function buildContext(request: ContextRequest): Promise<ContextPackage> {
  return apiRequest<ContextPackage>("/context/build", { method: "POST", body: request });
}

export function debugContext(request: ContextRequest): Promise<ContextDebug> {
  return apiRequest<ContextDebug>("/context/debug", { method: "POST", body: request });
}
