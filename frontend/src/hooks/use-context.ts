"use client";

import { useMutation } from "@tanstack/react-query";

import { debugContext } from "@/services/context";
import type { ContextRequest } from "@/types/context";

export function useContextDebug() {
  return useMutation({
    mutationFn: (request: ContextRequest) => debugContext(request),
  });
}
