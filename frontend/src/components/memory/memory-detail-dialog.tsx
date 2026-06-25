"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Archive, ArrowUpRight, Pencil, RotateCcw, Share2, Star, Trash2, Zap } from "lucide-react";

import { MemoryInsights } from "@/components/memory/memory-insights";
import { MemoryTypeBadge } from "@/components/shared/memory-type-badge";
import { ScoreBar } from "@/components/shared/score-bar";
import { StatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { useMemoryActions, useUpdateMemory } from "@/hooks/use-memory-actions";
import { formatDateTime } from "@/lib/utils";
import type { Memory } from "@/types/memory";

interface Props {
  memory: Memory | null;
  userId: string;
  onOpenChange: (open: boolean) => void;
}

export function MemoryDetailDialog({ memory, userId, onOpenChange }: Props) {
  const actions = useMemoryActions(userId);
  const update = useUpdateMemory(userId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  useEffect(() => {
    setEditing(false);
    setDraft(memory?.content ?? "");
  }, [memory]);
  const open = memory !== null;
  const busy = actions.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-2xl overflow-y-auto">
        {memory ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                Memory
                {memory.is_promoted ? (
                  <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
                ) : null}
              </DialogTitle>
              <DialogDescription className="font-mono text-xs">{memory.id}</DialogDescription>
            </DialogHeader>

            {editing ? (
              <div className="space-y-2">
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={4}
                  className="text-sm"
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={busy || !draft.trim() || draft === memory.content}
                    onClick={() =>
                      update.mutate(
                        { memoryId: memory.id, content: draft.trim() },
                        { onSuccess: () => setEditing(false) },
                      )
                    }
                  >
                    Save
                  </Button>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-sm leading-relaxed">{memory.content}</p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <MemoryTypeBadge type={memory.memory_type} />
              <StatusBadge status={memory.status} />
              <span className="text-xs text-muted-foreground">v{memory.version}</span>
              <span className="text-xs text-muted-foreground">priority {memory.priority}</span>
            </div>

            <ScoreBar score={memory.total_score} />

            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <span>Created {formatDateTime(memory.created_at)}</span>
              <span>Updated {formatDateTime(memory.updated_at)}</span>
            </div>

            <Separator />

            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => {
                  setDraft(memory.content);
                  setEditing(true);
                }}
              >
                <Pencil className="h-4 w-4" /> Edit
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => actions.mutate({ action: "reinforce", memoryId: memory.id })}
              >
                <Zap className="h-4 w-4" /> Reinforce
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => actions.mutate({ action: "promote", memoryId: memory.id })}
              >
                <Star className="h-4 w-4" /> Promote
              </Button>
              {memory.status === "archived" ? (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={() => actions.mutate({ action: "restore", memoryId: memory.id })}
                >
                  <RotateCcw className="h-4 w-4" /> Restore
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={() => actions.mutate({ action: "archive", memoryId: memory.id })}
                >
                  <Archive className="h-4 w-4" /> Archive
                </Button>
              )}
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => {
                  actions.mutate({ action: "delete", memoryId: memory.id });
                  onOpenChange(false);
                }}
              >
                <Trash2 className="h-4 w-4" /> Delete
              </Button>
              <Button size="sm" variant="outline" asChild>
                <Link href={`/graph?memory=${memory.id}`}>
                  <Share2 className="h-4 w-4" /> View in graph
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>

            <Separator />

            {/* Explainability: why this exists/was retrieved, lifecycle,
                contradiction lineage, relationships, summary membership. */}
            <MemoryInsights memory={memory} userId={userId} />
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
