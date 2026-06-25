"use client";

import { ArrowRight } from "lucide-react";

import { cn, formatDateTime, formatScore } from "@/lib/utils";
import type { MemoryEvidence } from "@/types/memory";

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-2.5">
      <div className="text-gradient text-lg font-semibold tabular-nums">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

/** Tiny inline sparkline over a real numeric history (no library). */
function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) {
    return <span className="text-xs text-muted-foreground">one data point</span>;
  }
  const w = 160;
  const h = 36;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => `${(i / (values.length - 1)) * w},${h - ((v - min) / span) * h}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-9 w-full" preserveAspectRatio="none">
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function healthLabel(conf: number, freshness: number): { label: string; color: string } {
  if (freshness < 0.15) return { label: "Stale", color: "text-amber-600" };
  if (conf >= 0.8) return { label: "Excellent", color: "text-emerald-600" };
  if (conf >= 0.55) return { label: "Good", color: "text-sky-600" };
  return { label: "Weak", color: "text-zinc-600" };
}

export function MemoryEvolution({ evidence }: { evidence: MemoryEvidence }) {
  const conf = evidence.confidence_history.at(-1) ?? 0;
  const imp = evidence.importance_history.at(-1) ?? 0;
  const stage = evidence.progression_history.at(-1) ?? "initial";
  const daysSince = Math.max(
    0,
    (Date.now() - new Date(evidence.last_seen).getTime()) / 86_400_000,
  );
  const freshness = Math.max(0, 1 - daysSince / 30);
  const stability = Math.min(1, evidence.reinforcement_count / 5);
  const health = healthLabel(conf, freshness);

  return (
    <div className="space-y-4">
      {/* Evolution stat cards */}
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        <Tile label="Confidence" value={formatScore(conf)} />
        <Tile label="Importance" value={formatScore(imp)} />
        <Tile label="Reinforced" value={evidence.reinforcement_count} />
        <Tile label="Evidence" value={evidence.evidence_count} />
        <Tile label="Stage" value={stage} />
        <Tile label="Stability" value={formatScore(stability)} />
        <Tile label="Freshness" value={formatScore(freshness)} />
        <Tile label="Source" value={evidence.source_type} />
      </div>

      {/* Health badge */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">Memory health:</span>
        <span className={cn("font-semibold", health.color)}>{health.label}</span>
      </div>

      {/* Confidence evolution */}
      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>Confidence evolution</span>
          <span className="tabular-nums">
            {evidence.confidence_history.map((v) => formatScore(v)).join(" → ")}
          </span>
        </div>
        <Sparkline values={evidence.confidence_history} color="#34d399" />
      </div>

      {/* Importance evolution */}
      <div>
        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>Importance evolution</span>
          <span className="tabular-nums">
            {evidence.importance_history.map((v) => formatScore(v)).join(" → ")}
          </span>
        </div>
        <Sparkline values={evidence.importance_history} color="#818cf8" />
      </div>

      {/* Stage progression */}
      {evidence.progression_history.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {evidence.progression_history.map((s, i) => (
            <span key={`${s}-${i}`} className="flex items-center gap-1.5">
              {i > 0 ? <ArrowRight className="h-3 w-3 text-muted-foreground" /> : null}
              <span className="rounded-full border border-border bg-card px-2 py-0.5 text-xs capitalize text-foreground/90">
                {s}
              </span>
            </span>
          ))}
        </div>
      ) : null}

      {/* Reason history */}
      {evidence.reason_history.length > 0 ? (
        <ol className="space-y-1.5 border-l border-border pl-3 text-sm">
          {evidence.reason_history.map((r, i) => (
            <li key={`${r}-${i}`} className="text-foreground/85">
              {r}
            </li>
          ))}
        </ol>
      ) : null}

      {/* Topics + seen window */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>First seen {formatDateTime(evidence.first_seen)}</span>
        <span>Last reinforced {formatDateTime(evidence.last_seen)}</span>
        {evidence.topic_history.length ? (
          <span>Topics: {[...new Set(evidence.topic_history)].join(", ")}</span>
        ) : null}
      </div>
    </div>
  );
}
