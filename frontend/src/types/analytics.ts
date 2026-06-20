export interface Analytics {
  total_memories: number;
  active_memories: number;
  archived_memories: number;
  promoted_memories: number;
  average_score: number;
  score_distribution: Record<string, number>;
}
