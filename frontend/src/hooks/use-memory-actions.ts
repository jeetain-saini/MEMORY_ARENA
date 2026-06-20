"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "@/lib/api-client";
import {
  archiveMemory,
  deleteMemory,
  promoteMemory,
  reinforceMemory,
} from "@/services/memories";

type Action = "reinforce" | "promote" | "archive" | "delete";

/** Memory-intelligence mutations with toast feedback + cache invalidation. */
export function useMemoryActions(userId: string) {
  const qc = useQueryClient();

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["memories"] });
    qc.invalidateQueries({ queryKey: ["analytics", userId] });
    qc.invalidateQueries({ queryKey: ["memory"] });
  };

  return useMutation<unknown, Error, { action: Action; memoryId: string }>({
    mutationFn: ({ action, memoryId }) => {
      switch (action) {
        case "reinforce":
          return reinforceMemory(memoryId, userId);
        case "promote":
          return promoteMemory(memoryId, userId);
        case "archive":
          return archiveMemory(memoryId, userId);
        case "delete":
          return deleteMemory(memoryId, userId);
      }
    },
    onSuccess: (_data, { action }) => {
      toast.success(`Memory ${action}d`);
      invalidate();
    },
    onError: (error, { action }) => {
      const message = error instanceof ApiError ? error.message : `Could not ${action} memory`;
      toast.error(message);
    },
  });
}
