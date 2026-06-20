import type { MemoryType } from "@/types/api";

export interface AgentCitation {
  memory_id: string;
  content: string;
  memory_type: MemoryType;
  provenance: string;
  score: number;
}

export interface QueryResponse {
  answer: string;
  citations: AgentCitation[];
  finish_reason: string;
}

// --- streaming (SSE) -------------------------------------------------------

export interface AgentStepEvent {
  step: string;
  ok: boolean;
  summary?: string;
  error?: string | null;
  tool?: string | null;
}

/** One parsed SSE frame from `/query/stream`. */
export type AgentStreamEvent =
  | { event: "step"; data: AgentStepEvent }
  | { event: "answer"; data: { answer: string } }
  | { event: "citations"; data: { citations: AgentCitation[] } }
  | { event: "error"; data: { finish_reason?: string; message?: string } }
  | { event: "done"; data: { finish_reason: string; answer?: string; citations?: AgentCitation[] } };

export type AgentRunStatus = "idle" | "streaming" | "done" | "error";

export interface AgentRunState {
  status: AgentRunStatus;
  steps: AgentStepEvent[];
  answer: string;
  citations: AgentCitation[];
  finishReason: string | null;
  error: string | null;
}
