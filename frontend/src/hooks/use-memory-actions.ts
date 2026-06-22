"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api-client";
import {
  archiveMemory,
  deleteMemory,
  promoteMemory,
  reinforceMemory,
  resolveContradiction,
  restoreMemory,
  updateMemory,
} from "@/services/memories";

type Action = "reinforce" | "promote" | "archive" | "restore" | "delete";

function invalidateMemoryQueries(qc: ReturnType<typeof useQueryClient>, userId: string) {
  qc.invalidateQueries({ queryKey: ["memories"] });
  qc.invalidateQueries({ queryKey: ["analytics", userId] });
  qc.invalidateQueries({ queryKey: ["memory"] });
  qc.invalidateQueries({ queryKey: ["graph"] });
}

/** Memory-intelligence + lifecycle mutations with toast feedback + invalidation. */
export function useMemoryActions(userId: string) {
  const qc = useQueryClient();

  return useMutation<unknown, Error, { action: Action; memoryId: string }>({
    mutationFn: ({ action, memoryId }) => {
      switch (action) {
        case "reinforce":
          return reinforceMemory(memoryId, userId);
        case "promote":
          return promoteMemory(memoryId, userId);
        case "archive":
          return archiveMemory(memoryId, userId);
        case "restore":
          return restoreMemory(memoryId, userId);
        case "delete":
          return deleteMemory(memoryId, userId);
      }
    },
    onSuccess: (_data, { action }) => {
      toast.success(`Memory ${action}d`);
      invalidateMemoryQueries(qc, userId);
    },
    onError: (error, { action }) => {
      const message = error instanceof ApiError ? error.message : `Could not ${action} memory`;
      toast.error(message);
    },
  });
}

/** Edit a memory's content (records a new version; audit history preserved). */
export function useUpdateMemory(userId: string) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { memoryId: string; content: string }>({
    mutationFn: ({ memoryId, content }) => updateMemory(memoryId, userId, content),
    onSuccess: () => {
      toast.success("Memory updated");
      invalidateMemoryQueries(qc, userId);
    },
    onError: (error) => {
      const message = error instanceof ApiError ? error.message : "Could not update memory";
      toast.error(message);
    },
  });
}

/** Resolve a contradiction: keep one memory, archive the obsolete one. */
export function useResolveContradiction(userId: string) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { keepId: string; archiveId: string }>({
    mutationFn: ({ keepId, archiveId }) => resolveContradiction(userId, keepId, archiveId),
    onSuccess: () => {
      toast.success("Contradiction resolved");
      invalidateMemoryQueries(qc, userId);
    },
    onError: (error) => {
      const message =
        error instanceof ApiError ? error.message : "Could not resolve contradiction";
      toast.error(message);
    },
  });
}
