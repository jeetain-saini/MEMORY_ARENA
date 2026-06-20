"use client";

import { useCallback, useRef, useState } from "react";

import { readAgentStream } from "@/lib/sse";
import { queryAgentStream } from "@/services/agent";
import type { AgentRunState } from "@/types/agent";

const INITIAL: AgentRunState = {
  status: "idle",
  steps: [],
  answer: "",
  citations: [],
  finishReason: null,
  error: null,
};

/** Drives the SSE agent stream: step/answer/citations/done with cancellation. */
export function useAgentStream() {
  const [state, setState] = useState<AgentRunState>(INITIAL);
  const controllerRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const run = useCallback(
    async (userId: string, query: string) => {
      cancel();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ ...INITIAL, status: "streaming" });

      try {
        const response = await queryAgentStream(userId, query, controller.signal);
        for await (const event of readAgentStream(response)) {
          if (event.event === "step") {
            setState((s) => ({ ...s, steps: [...s.steps, event.data] }));
          } else if (event.event === "answer") {
            setState((s) => ({ ...s, answer: event.data.answer }));
          } else if (event.event === "citations") {
            setState((s) => ({ ...s, citations: event.data.citations }));
          } else if (event.event === "error") {
            setState((s) => ({
              ...s,
              status: "error",
              error: event.data.message ?? event.data.finish_reason ?? "stream error",
            }));
          } else if (event.event === "done") {
            setState((s) => ({
              ...s,
              status: s.status === "error" ? "error" : "done",
              finishReason: event.data.finish_reason,
              answer: event.data.answer ?? s.answer,
              citations: event.data.citations ?? s.citations,
            }));
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          setState((s) => ({ ...s, status: "done", finishReason: "cancelled" }));
        } else {
          setState((s) => ({
            ...s,
            status: "error",
            error: error instanceof Error ? error.message : "request failed",
          }));
        }
      } finally {
        controllerRef.current = null;
      }
    },
    [cancel],
  );

  const reset = useCallback(() => {
    cancel();
    setState(INITIAL);
  }, [cancel]);

  return { state, run, cancel, reset };
}
