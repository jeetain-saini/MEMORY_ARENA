import type { MemoryCategory, MemoryStatus, MemoryType } from "@/types/api";

// Phase C/D: append-only evidence stored in metadata.evidence (read-only).
export interface MemoryEvidence {
  first_seen: string;
  last_seen: string;
  created_from_message: string;
  latest_message: string;
  source_type: string;
  evidence_count: number;
  reinforcement_count: number;
  conversation_ids: string[];
  message_ids: string[];
  confidence_history: number[];
  importance_history: number[];
  reason_history: string[];
  topic_history: string[];
  progression_history: string[];
}

export interface MemoryMetadata {
  evidence?: MemoryEvidence;
  reason_for_inference?: string;
  inference_topic?: string;
  progression_stage?: string;
  original_text?: string;
  [key: string]: unknown;
}

export interface Memory {
  id: string;
  user_id: string;
  content: string;
  memory_type: MemoryType;
  status: MemoryStatus;
  total_score: number;
  version: number;
  is_promoted: boolean;
  priority: number;
  category?: MemoryCategory | null;
  retrieval_count?: number;
  created_at: string;
  updated_at: string;
  metadata?: MemoryMetadata | null;
}

export interface CreateMemoryRequest {
  user_id: string;
  content: string;
  memory_type: MemoryType;
  metadata?: Record<string, unknown>;
}

export interface MemorySearchRequest {
  user_id: string;
  query?: string | null;
  memory_types?: MemoryType[] | null;
  statuses?: MemoryStatus[] | null;
  min_total_score?: number | null;
  limit?: number;
  offset?: number;
}
