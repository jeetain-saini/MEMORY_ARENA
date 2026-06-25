import type { MemoryStatus, MemoryType } from "@/types/api";
import type { Memory } from "@/types/memory";
import type { MemorySummary } from "@/types/summary";

// A single point on the memory timeline / activity feed, derived purely from the
// timestamps the existing APIs already return (memory created_at/updated_at +
// lifecycle status, summary updated_at). No new backend, schema, or events.
export type MemoryEventKind =
  | "created"
  | "updated"
  | "promoted"
  | "archived"
  | "superseded"
  | "forgotten"
  | "summary";

export interface MemoryEvent {
  id: string;
  kind: MemoryEventKind;
  at: string; // ISO timestamp
  title: string;
  detail: string;
  memoryType?: MemoryType;
  status?: MemoryStatus;
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Derive a newest-first event stream from a user's memories and summaries. */
export function deriveMemoryEvents(
  memories: Memory[],
  summaries: MemorySummary[] = [],
): MemoryEvent[] {
  const events: MemoryEvent[] = [];

  for (const m of memories) {
    events.push({
      id: `${m.id}:created`,
      kind: "created",
      at: m.created_at,
      title: "Memory created",
      detail: m.content,
      memoryType: m.memory_type,
      status: m.status,
    });

    // One representative lifecycle event at updated_at (avoids duplicate noise).
    const base = {
      detail: m.content,
      memoryType: m.memory_type,
      status: m.status,
      at: m.updated_at,
    };
    if (m.status === "archived") {
      events.push({ id: `${m.id}:archived`, kind: "archived", title: "Memory archived", ...base });
    } else if (m.status === "superseded") {
      events.push({
        id: `${m.id}:superseded`,
        kind: "superseded",
        title: "Memory superseded",
        ...base,
      });
    } else if (m.status === "forgotten") {
      events.push({
        id: `${m.id}:forgotten`,
        kind: "forgotten",
        title: "Memory forgotten",
        ...base,
      });
    } else if (m.is_promoted) {
      events.push({ id: `${m.id}:promoted`, kind: "promoted", title: "Memory promoted", ...base });
    } else if (m.updated_at !== m.created_at) {
      events.push({ id: `${m.id}:updated`, kind: "updated", title: "Memory updated", ...base });
    }
  }

  for (const s of summaries) {
    events.push({
      id: `${s.id}:summary`,
      kind: "summary",
      at: s.updated_at ?? s.created_at,
      title: `${cap(String(s.scope))} summary refreshed`,
      detail: s.summary_text,
    });
  }

  return events.sort((a, b) => +new Date(b.at) - +new Date(a.at));
}

export interface MonthGroup {
  key: string; // e.g. "2026-07"
  label: string; // e.g. "July 2026"
  events: MemoryEvent[];
}

/** Group events into chronological month buckets (newest month first). */
export function groupByMonth(events: MemoryEvent[]): MonthGroup[] {
  const map = new Map<string, MonthGroup>();
  for (const e of events) {
    const d = new Date(e.at);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    let group = map.get(key);
    if (!group) {
      group = { key, label, events: [] };
      map.set(key, group);
    }
    group.events.push(e);
  }
  return [...map.values()].sort((a, b) => (a.key < b.key ? 1 : -1));
}
