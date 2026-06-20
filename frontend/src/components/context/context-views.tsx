import { AlertTriangle, Layers, Scissors } from "lucide-react";

import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { StatCard } from "@/components/shared/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatScore } from "@/lib/utils";
import type { ContextDebug } from "@/types/context";

export function ContextPackageView({ debug }: { debug: ContextDebug }) {
  const pkg = debug.package;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatCard title="Tokens used" value={`${pkg.total_tokens} / ${pkg.max_tokens}`} />
        <StatCard title="Memories" value={pkg.memories.length} />
        <StatCard title="Conflicts" value={debug.conflicts.length} />
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Assembled context</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-xs leading-relaxed">
            {pkg.context_text || "(empty)"}
          </pre>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Included memories</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {pkg.memories.map((m) => (
            <div key={m.memory_id} className="flex items-center justify-between gap-3 text-sm">
              <span className="line-clamp-1">{m.content}</span>
              <div className="flex shrink-0 items-center gap-2">
                <MemoryTypeBadge type={m.memory_type} />
                <span className="text-xs text-muted-foreground">{m.tokens}t</span>
                <span className="text-xs tabular-nums">{formatScore(m.score)}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {debug.conflicts.length > 0 ? (
        <Card>
          <CardHeader className="flex-row items-center gap-2 pb-3">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <CardTitle className="text-sm">Conflicts detected</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {debug.conflicts.map((c, i) => (
              <div key={i} className="rounded-md border border-amber-200 bg-amber-50 p-2 text-amber-900">
                <p className="text-xs font-medium uppercase">{c.reason}</p>
                <p>“{c.content_a}”</p>
                <p>“{c.content_b}”</p>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {debug.consolidations.length > 0 ? (
        <Card>
          <CardHeader className="flex-row items-center gap-2 pb-3">
            <Layers className="h-4 w-4 text-sky-500" />
            <CardTitle className="text-sm">Consolidations</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs text-muted-foreground">
            {debug.consolidations.map((c, i) => (
              <p key={i}>
                kept <span className="font-mono">{c.kept_memory_id.slice(0, 8)}</span> · removed{" "}
                {c.removed_memory_ids.length}
              </p>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export function CompressionView({ debug }: { debug: ContextDebug }) {
  const c = debug.compression;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard title="Original tokens" value={c.original_tokens} />
        <StatCard title="Compressed" value={c.compressed_tokens} />
        <StatCard title="Ratio" value={`${Math.round(c.ratio * 100)}%`} />
        <StatCard title="Removed" value={c.removed_memories} />
      </div>

      {debug.dropped.length > 0 ? (
        <Card>
          <CardHeader className="flex-row items-center gap-2 pb-3">
            <Scissors className="h-4 w-4 text-rose-500" />
            <CardTitle className="text-sm">Dropped memories</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {debug.dropped.map((d, i) => (
              <div key={i} className="flex items-center justify-between gap-3">
                <span className="line-clamp-1 text-muted-foreground">{d.content}</span>
                <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs">{d.reason}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
