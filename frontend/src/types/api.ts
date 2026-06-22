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

export type MemoryStatus =
  | "active"
  | "archived"
  | "superseded"
  | "forgotten"
  | "deleted";

export const MEMORY_STATUSES: MemoryStatus[] = [
  "active",
  "archived",
  "superseded",
  "forgotten",
  "deleted",
];

export type MemoryCategory = "episodic" | "semantic";

export type GraphEdgeType =
  | "related_to"
  | "supports"
  | "used_in"
  | "depends_on"
  | "derived_from"
  | "reinforces"
  | "contradicts"
  | "supersedes"
  | "promoted_from"
  | "cluster_member";

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
