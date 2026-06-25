"use client";

import {
  Archive,
  ArrowRightLeft,
  EyeOff,
  Pencil,
  Plus,
  ScrollText,
  Star,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState, LoadingRows, NoUserState } from "@/components/shared/states";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useUserMemories } from "@/hooks/use-memories";
import { useSummaries } from "@/hooks/use-summaries";
import {
  deriveMemoryEvents,
  groupByMonth,
  type MemoryEventKind,
} from "@/lib/memory-events";
import { cn, formatDateTime } from "@/lib/utils";

const KIND_META: Record<MemoryEventKind, { label: string; icon: LucideIcon; color: string }> = {
  created: { label: "Created", icon: Plus, color: "text-emerald-600" },
  updated: { label: "Updated", icon: Pencil, color: "text-sky-600" },
  promoted: { label: "Promoted", icon: Star, color: "text-amber-600" },
  archived: { label: "Archived", icon: Archive, color: "text-zinc-600" },
  superseded: { label: "Superseded", icon: ArrowRightLeft, color: "text-violet-600" },
  forgotten: { label: "Forgotten", icon: EyeOff, color: "text-orange-600" },
  summary: { label: "Summary", icon: ScrollText, color: "text-primary" },
};

const ALL_KINDS = Object.keys(KIND_META) as MemoryEventKind[];
const PAGE_SIZE = 40;

export default function TimelinePage() {
  const { userId, ready, hasUser } = useCurrentUser();
  // Backend caps the list endpoint at limit<=100 (Query(le=100)); 100 is the max.
  const memories = useUserMemories(userId, 100);
  const summaries = useSummaries(userId);
  const [active, setActive] = useState<Set<MemoryEventKind>>(new Set(ALL_KINDS));
  const [visible, setVisible] = useState(PAGE_SIZE);

  const events = useMemo(
    () => deriveMemoryEvents(memories.data ?? [], summaries.data ?? []),
    [memories.data, summaries.data],
  );
  const filtered = useMemo(() => events.filter((e) => active.has(e.kind)), [events, active]);
  const groups = useMemo(() => groupByMonth(filtered.slice(0, visible)), [filtered, visible]);

  const toggle = (kind: MemoryEventKind) =>
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next.size === 0 ? new Set(ALL_KINDS) : next;
    });

  if (!ready) return <LoadingRows rows={5} />;
  if (!hasUser) return <NoUserState />;

  return (
    <div>
      <PageHeader
        title="Memory Timeline"
        description="How your memory has evolved — creations, updates, supersessions, and summaries over time."
      />

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-2">
        {ALL_KINDS.map((kind) => {
          const { label, icon: Icon, color } = KIND_META[kind];
          const on = active.has(kind);
          return (
            <button
              key={kind}
              type="button"
              onClick={() => toggle(kind)}
              aria-pressed={on}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                on
                  ? "border-border bg-card text-foreground"
                  : "border-border bg-transparent text-muted-foreground hover:bg-accent",
              )}
            >
              <Icon className={cn("h-3.5 w-3.5", on ? color : "")} />
              {label}
            </button>
          );
        })}
      </div>

      {memories.isError ? (
        <ErrorState error={memories.error} />
      ) : memories.isLoading ? (
        <LoadingRows rows={6} />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No timeline activity yet"
          description="Capture memories through the Agent Playground or POST /api/v1/ingest to see them appear here."
        />
      ) : (
        <div className="space-y-10">
          {groups.map((group) => (
            <section key={group.key}>
              <h2 className="font-playfair mb-4 text-xl italic text-foreground/90">
                {group.label}
              </h2>
              <ol className="relative ml-3 space-y-3 border-l border-border pl-6">
                {group.events.map((e) => {
                  const { icon: Icon, color, label } = KIND_META[e.kind];
                  return (
                    <li key={e.id} className="relative">
                      {/* node dot on the timeline rail */}
                      <span className="absolute -left-[31px] top-3 flex h-5 w-5 items-center justify-center rounded-full border border-border bg-background">
                        <Icon className={cn("h-3 w-3", color)} />
                      </span>
                      <div className="lift rounded-xl border border-border bg-card p-4 ">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={cn("text-xs font-semibold uppercase tracking-wide", color)}>
                            {label}
                          </span>
                          {e.memoryType ? <MemoryTypeBadge type={e.memoryType} /> : null}
                          <span className="ml-auto text-xs text-muted-foreground">
                            {formatDateTime(e.at)}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-foreground/90">
                          {e.detail}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </section>
          ))}

          {visible < filtered.length ? (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => setVisible((v) => v + PAGE_SIZE)}
                className="rounded-full border border-border bg-card px-5 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                Load more ({filtered.length - visible} older)
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
