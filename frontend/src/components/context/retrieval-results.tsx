import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { ScoreBar } from "@/components/shared/score-bar";
import { Card, CardContent } from "@/components/ui/card";
import { formatScore } from "@/lib/utils";
import type { RetrievedMemory } from "@/types/retrieval";

export function RetrievalResults({ results }: { results: RetrievedMemory[] }) {
  return (
    <div className="space-y-3">
      {results.map((r, i) => (
        <Card key={r.memory_id}>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm">
                <span className="mr-2 text-xs text-muted-foreground">#{i + 1}</span>
                {r.content}
              </p>
              <MemoryTypeBadge type={r.memory_type} />
            </div>
            <ScoreBar score={r.final_score} />
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-4">
              <span>vector {formatScore(r.scores.vector_score)}</span>
              <span>bm25 {formatScore(r.scores.bm25_score)}</span>
              <span>memory {formatScore(r.scores.memory_score)}</span>
              <span>recency {formatScore(r.scores.recency_score)}</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
