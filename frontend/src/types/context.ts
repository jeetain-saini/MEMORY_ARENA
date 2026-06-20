import type { MemoryStatus, MemoryType } from "@/types/api";

export interface ContextRequest {
  query: string;
  user_id: string;
  max_tokens?: number;
  top_k?: number;
  filters?: { memory_types?: MemoryType[] | null; statuses?: MemoryStatus[] | null } | null;
  metadata?: Record<string, unknown>;
}

export interface ContextMemory {
  memory_id: string;
  content: string;
  memory_type: MemoryType;
  status: MemoryStatus;
  score: number;
  tokens: number;
  is_promoted: boolean;
}

export interface ContextPackage {
  query: string;
  user_id: string;
  total_tokens: number;
  max_tokens: number;
  context_text: string;
  memories: ContextMemory[];
  metadata: Record<string, unknown>;
}

export interface DroppedMemory {
  memory_id: string;
  content: string;
  reason: string;
}

export interface ConflictRecord {
  memory_id_a: string;
  memory_id_b: string;
  reason: string;
  content_a: string;
  content_b: string;
}

export interface ConsolidationRecord {
  kept_memory_id: string;
  removed_memory_ids: string[];
  reason: string;
}

export interface CompressionStats {
  original_tokens: number;
  compressed_tokens: number;
  ratio: number;
  removed_memories: number;
}

export interface ContextDebug {
  package: ContextPackage;
  selected: ContextMemory[];
  dropped: DroppedMemory[];
  conflicts: ConflictRecord[];
  consolidations: ConsolidationRecord[];
  compression: CompressionStats;
}
