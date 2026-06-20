import type { MemoryType } from "@/types/api";

// Shape the dashboard expects once a summaries read endpoint exists
// (GET /api/v1/summaries/{user_id}). No such endpoint ships in Stage 11, so the
// Summary Explorer degrades gracefully until it is added.
export interface MemorySummary {
  id: string;
  user_id: string;
  scope: MemoryType;
  summary_text: string;
  source_memory_ids: string[];
  source_count: number;
  version: number;
  created_at: string;
  updated_at: string;
}
