import type { MemoryCategory, MemoryStatus, MemoryType } from "@/types/api";

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
