"use client";

import { useMutation } from "@tanstack/react-query";

import { retrievalDebug } from "@/services/retrieval";
import type { RetrievalSearchRequest } from "@/types/retrieval";

export function useRetrievalDebug() {
  return useMutation({
    mutationFn: (request: RetrievalSearchRequest) => retrievalDebug(request),
  });
}
