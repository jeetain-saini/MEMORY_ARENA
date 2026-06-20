"use client";

import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { MEMORY_STATUSES, MEMORY_TYPES, type MemoryStatus, type MemoryType } from "@/types/api";
import { cn } from "@/lib/utils";

interface FilterBarProps {
  query: string;
  onQuery: (value: string) => void;
  types: MemoryType[];
  onToggleType: (type: MemoryType) => void;
  statuses: MemoryStatus[];
  onToggleStatus: (status: MemoryStatus) => void;
}

function Toggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-2.5 py-1 text-xs font-medium capitalize transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-input text-muted-foreground hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}

export function FilterBar({
  query,
  onQuery,
  types,
  onToggleType,
  statuses,
  onToggleStatus,
}: FilterBarProps) {
  return (
    <div className="space-y-3 rounded-lg border bg-card p-4">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search memories…"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          className="pl-9"
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <span className="text-xs font-medium text-muted-foreground">Type</span>
        {MEMORY_TYPES.map((t) => (
          <Toggle key={t} active={types.includes(t)} onClick={() => onToggleType(t)}>
            {t}
          </Toggle>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <span className="text-xs font-medium text-muted-foreground">Status</span>
        {MEMORY_STATUSES.map((s) => (
          <Toggle key={s} active={statuses.includes(s)} onClick={() => onToggleStatus(s)}>
            {s}
          </Toggle>
        ))}
      </div>
    </div>
  );
}
