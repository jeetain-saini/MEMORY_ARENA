import { EDGE_STYLES } from "@/lib/constants";
import type { GraphEdgeType } from "@/types/api";

export function EdgeLegend({ present }: { present?: Set<GraphEdgeType> }) {
  const entries = (Object.keys(EDGE_STYLES) as GraphEdgeType[]).filter(
    (t) => !present || present.has(t),
  );
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-3 rounded-md border bg-card/80 p-2 text-xs">
      {entries.map((type) => {
        const style = EDGE_STYLES[type];
        return (
          <div key={type} className="flex items-center gap-1.5">
            <svg width="22" height="8" aria-hidden>
              <line
                x1="0"
                y1="4"
                x2="22"
                y2="4"
                stroke={style.color}
                strokeWidth="2"
                strokeDasharray={style.dashed ? "4 3" : undefined}
              />
            </svg>
            <span className="text-muted-foreground">{style.label}</span>
          </div>
        );
      })}
    </div>
  );
}
