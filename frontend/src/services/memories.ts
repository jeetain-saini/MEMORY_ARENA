import { apiRequest } from "@/lib/api-client";
import type { Memory, MemorySearchRequest } from "@/types/memory";

export interface ContradictionResolution {
  kept: Memory;
  archived: Memory;
  superseded_edge: boolean;
  contradiction_preserved: boolean;
}

export function listUserMemories(
  userId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Memory[]> {
  return apiRequest<Memory[]>(`/memories/user/${userId}`, {
    query: { limit: params.limit ?? 50, offset: params.offset ?? 0 },
  });
}

export function searchMemories(request: MemorySearchRequest): Promise<Memory[]> {
  return apiRequest<Memory[]>("/memories/search", { method: "POST", body: request });
}

export function getMemory(memoryId: string): Promise<Memory> {
  return apiRequest<Memory>(`/memories/${memoryId}`);
}

export function reinforceMemory(memoryId: string, userId: string): Promise<Memory> {
  return apiRequest<Memory>(`/memories/${memoryId}/reinforce`, {
    method: "POST",
    query: { user_id: userId },
  });
}

export function promoteMemory(memoryId: string, userId: string): Promise<Memory> {
  return apiRequest<Memory>(`/memories/${memoryId}/promote`, {
    method: "POST",
    query: { user_id: userId },
  });
}

export function archiveMemory(
  memoryId: string,
  userId: string,
  force = false,
): Promise<Memory> {
  return apiRequest<Memory>(`/memories/${memoryId}/archive`, {
    method: "POST",
    query: { user_id: userId, force },
  });
}

export function deleteMemory(
  memoryId: string,
  userId: string,
): Promise<{ memory_id: string; deleted: boolean }> {
  return apiRequest(`/memories/${memoryId}`, {
    method: "DELETE",
    query: { user_id: userId },
  });
}

export function updateMemory(
  memoryId: string,
  userId: string,
  content: string,
): Promise<Memory> {
  return apiRequest<Memory>(`/memories/${memoryId}`, {
    method: "PUT",
    body: { user_id: userId, content, reason: "edited via dashboard" },
  });
}

export function restoreMemory(memoryId: string, userId: string): Promise<Memory> {
  return apiRequest<Memory>(`/memories/${memoryId}/restore`, {
    method: "POST",
    query: { user_id: userId },
  });
}

export function resolveContradiction(
  userId: string,
  keepId: string,
  archiveId: string,
): Promise<ContradictionResolution> {
  return apiRequest<ContradictionResolution>("/memories/contradictions/resolve", {
    method: "POST",
    body: { user_id: userId, keep_id: keepId, archive_id: archiveId },
  });
}
