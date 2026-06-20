import type { MemoryStatus, MemoryType } from "@/types/api";

export interface RetrievalFilters {
  memory_types?: MemoryType[] | null;
  statuses?: MemoryStatus[] | null;
}

export interface RetrievalSearchRequest {
  query: string;
  user_id: string;
  top_k?: number;
  filters?: RetrievalFilters | null;
}

export interface ScoreBreakdown {
  vector_score: number;
  bm25_score: number;
  memory_score: number;
  recency_score: number;
  final_score: number;
}

export interface RetrievedMemory {
  memory_id: string;
  user_id: string;
  content: string;
  memory_type: MemoryType;
  status: MemoryStatus;
  final_score: number;
  scores: ScoreBreakdown;
}

export interface RetrievalResult {
  query: string;
  user_id: string;
  count: number;
  results: RetrievedMemory[];
}
