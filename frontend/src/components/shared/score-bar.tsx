import { cn } from "@/lib/utils";
import { formatScore } from "@/lib/utils";

export function ScoreBar({ score, className }: { score: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  const tone =
    pct >= 65 ? "bg-emerald-500" : pct >= 30 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
        {formatScore(score)}
      </span>
    </div>
  );
}
