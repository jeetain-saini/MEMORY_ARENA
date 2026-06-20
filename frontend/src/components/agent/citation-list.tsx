import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { Badge } from "@/components/ui/badge";
import { formatScore } from "@/lib/utils";
import type { AgentCitation } from "@/types/agent";

export function CitationList({ citations }: { citations: AgentCitation[] }) {
  if (citations.length === 0) {
    return <p className="text-sm text-muted-foreground">No citations.</p>;
  }
  return (
    <div className="space-y-2">
      {citations.map((c) => (
        <div key={c.memory_id} className="rounded-md border p-3 text-sm">
          <div className="mb-1 flex items-center gap-2">
            <MemoryTypeBadge type={c.memory_type} />
            <Badge variant="secondary" className="capitalize">
              {c.provenance}
            </Badge>
            <span className="ml-auto text-xs tabular-nums text-muted-foreground">
              {formatScore(c.score)}
            </span>
          </div>
          <p>{c.content}</p>
        </div>
      ))}
    </div>
  );
}
