"use client";

import { useMemo, useState } from "react";

import { FilterBar } from "@/components/memory/filter-bar";
import { MemoryDetailDialog } from "@/components/memory/memory-detail-dialog";
import { MemoryCard } from "@/components/shared/memory-card";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState, LoadingRows, NoUserState } from "@/components/shared/states";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useMemorySearch } from "@/hooks/use-memories";
import type { MemoryStatus, MemoryType } from "@/types/api";
import type { Memory } from "@/types/memory";

export default function MemoriesPage() {
  const { userId, ready, hasUser } = useCurrentUser();
  const [query, setQuery] = useState("");
  const [types, setTypes] = useState<MemoryType[]>([]);
  const [statuses, setStatuses] = useState<MemoryStatus[]>([]);
  const [selected, setSelected] = useState<Memory | null>(null);

  const request = useMemo(
    () => ({
      user_id: userId,
      query: query.trim() || null,
      memory_types: types.length ? types : null,
      statuses: statuses.length ? statuses : null,
      limit: 100,
    }),
    [userId, query, types, statuses],
  );

  const search = useMemorySearch(request, hasUser);

  const toggle = <T,>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((x) => x !== value) : [...list, value];

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  return (
    <div>
      <PageHeader
        title="Memory Explorer"
        description="Search and filter memories; click one to inspect and act on it."
      />

      <FilterBar
        query={query}
        onQuery={setQuery}
        types={types}
        onToggleType={(t) => setTypes((prev) => toggle(prev, t))}
        statuses={statuses}
        onToggleStatus={(s) => setStatuses((prev) => toggle(prev, s))}
      />

      <div className="mt-6">
        {search.isError ? (
          <ErrorState error={search.error} />
        ) : search.isLoading ? (
          <LoadingRows rows={5} />
        ) : (search.data ?? []).length === 0 ? (
          <EmptyState
            title="No memories match"
            description="Try clearing filters or ingesting memories via POST /api/v1/ingest."
          />
        ) : (
          <>
            <p className="mb-3 text-sm text-muted-foreground">
              {search.data?.length} result{search.data?.length === 1 ? "" : "s"}
            </p>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {search.data?.map((m) => (
                <MemoryCard key={m.id} memory={m} onClick={() => setSelected(m)} />
              ))}
            </div>
          </>
        )}
      </div>

      <MemoryDetailDialog
        memory={selected}
        userId={userId}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  );
}
