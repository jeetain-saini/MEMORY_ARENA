"use client";

import { ChevronDown, Database, FileText, Share2, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { cn, formatScore } from "@/lib/utils";
import type { AgentCitation } from "@/types/agent";

// Map the retrieval provenance the backend returns to a friendly category.
const CATEGORY: Record<string, { label: string; icon: LucideIcon }> = {
  base: { label: "Retrieved memories", icon: Database },
  hybrid: { label: "Retrieved memories", icon: Database },
  vector: { label: "Retrieved memories", icon: Database },
  keyword: { label: "Retrieved memories", icon: Database },
  graph: { label: "Graph-expanded memories", icon: Share2 },
};
const categoryFor = (p: string) => CATEGORY[p] ?? { label: "Other sources", icon: FileText };

function SourceRow({ citation }: { citation: AgentCitation }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-lg border border-white/10 bg-white/[0.025]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <MemoryTypeBadge type={citation.memory_type} />
        <span className="min-w-0 flex-1 truncate text-sm text-foreground">{citation.content}</span>
        <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
          {formatScore(citation.score)}
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open ? (
        <div className="space-y-1.5 border-t border-white/10 px-3 py-2 text-xs">
          <p className="leading-relaxed text-foreground/90">{citation.content}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
            <span>
              Memory{" "}
              <span className="font-mono">#{citation.memory_id.slice(0, 8)}</span>
            </span>
            <span className="capitalize">provenance: {citation.provenance}</span>
            <span>retrieval score: {formatScore(citation.score)}</span>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function SourceAttribution({ citations }: { citations: AgentCitation[] }) {
  const [open, setOpen] = useState(true);

  const groups = useMemo(() => {
    const map = new Map<string, { icon: LucideIcon; items: AgentCitation[] }>();
    for (const c of citations) {
      const { label, icon } = categoryFor(c.provenance);
      const g = map.get(label) ?? { icon, items: [] };
      g.items.push(c);
      map.set(label, g);
    }
    return [...map.entries()];
  }, [citations]);

  if (citations.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No sources — the agent answered from general knowledge (no memories were retrieved).
      </p>
    );
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <span className="text-sm font-medium text-foreground">Sources Used</span>
        <span className="rounded-full border border-white/10 bg-white/[0.06] px-2 py-0.5 text-xs text-muted-foreground">
          {citations.length}
        </span>
        <ChevronDown
          className={cn(
            "ml-auto h-4 w-4 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open ? (
        <div className="space-y-4 px-4 pb-4">
          {groups.map(([label, { icon: Icon, items }]) => (
            <div key={label}>
              <div className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <Icon className="h-3.5 w-3.5" />
                {label}
                <span className="text-muted-foreground/70">({items.length})</span>
              </div>
              <ul className="space-y-2">
                {items.map((c) => (
                  <SourceRow key={`${c.memory_id}:${c.provenance}`} citation={c} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
