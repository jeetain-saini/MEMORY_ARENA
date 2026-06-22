// Wire-contract types mirroring the MemoryArena API (backend `schemas/`).

export type MemoryType =
  | "fact"
  | "goal"
  | "preference"
  | "skill"
  | "project"
  | "experience";

export const MEMORY_TYPES: MemoryType[] = [
  "fact",
  "goal",
  "preference",
  "skill",
  "project",
  "experience",
];

export type MemoryStatus = "active" | "archived" | "deleted";

export const MEMORY_STATUSES: MemoryStatus[] = ["active", "archived", "deleted"];

export type GraphEdgeType =
  | "related_to"
  | "supports"
  | "used_in"
  | "depends_on"
  | "derived_from"
  | "reinforces"
  | "contradicts"
  | "supersedes";

export type NodeType =
  | "memory"
  | "goal"
  | "skill"
  | "project"
  | "preference"
  | "fact";

/** Standard success envelope: `{ success, data, request_id }`. */
export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  request_id?: string | null;
}

/** Standard error envelope: `{ success:false, error:{...} }`. */
export interface ApiErrorBody {
  success: false;
  error: { code: string; message: string; details?: unknown };
  request_id?: string | null;
}
