import { cn } from "@/lib/utils";

/** Horizontal bars for the analytics score distribution buckets. */
export function DistributionBars({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="space-y-2">
      {entries.map(([label, value]) => (
        <div key={label} className="flex items-center gap-3">
          <span className="w-16 shrink-0 font-mono text-xs text-muted-foreground">{label}</span>
          <div className="h-3 w-full overflow-hidden rounded bg-muted">
            <div
              className={cn("h-full rounded bg-primary/70")}
              style={{ width: `${(value / max) * 100}%` }}
            />
          </div>
          <span className="w-8 shrink-0 text-right text-xs tabular-nums">{value}</span>
        </div>
      ))}
    </div>
  );
}
