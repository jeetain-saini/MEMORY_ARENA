import { Star } from "lucide-react";

import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { ScoreBar } from "@/components/shared/score-bar";
import { StatusBadge } from "@/components/shared/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/utils";
import type { Memory } from "@/types/memory";

interface MemoryCardProps {
  memory: Memory;
  onClick?: () => void;
  footer?: React.ReactNode;
}

export function MemoryCard({ memory, onClick, footer }: MemoryCardProps) {
  return (
    <Card
      className={cn(onClick && "cursor-pointer transition-colors hover:border-primary/40")}
      onClick={onClick}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm leading-relaxed">{memory.content}</p>
          {memory.is_promoted ? (
            <Star className="mt-0.5 h-4 w-4 shrink-0 fill-amber-400 text-amber-400" />
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <MemoryTypeBadge type={memory.memory_type} />
          <StatusBadge status={memory.status} />
          <span className="text-xs text-muted-foreground">
            updated {formatDateTime(memory.updated_at)}
          </span>
        </div>
        <ScoreBar score={memory.total_score} />
        {footer}
      </CardContent>
    </Card>
  );
}
