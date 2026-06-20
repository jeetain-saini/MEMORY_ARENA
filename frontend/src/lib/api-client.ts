// Type-safe fetch wrapper around the MemoryArena API.
//
// - Unwraps the standard `{ success, data }` envelope, returning `data`.
// - Throws `ApiError` (carrying the backend error code/message) on failure.
// - Exposes `apiStream` for the SSE endpoint (returns the raw Response so the
//   caller can read the body as a stream).

import type { ApiEnvelope, ApiErrorBody } from "@/types/api";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface RequestOptions {
  method?: string;
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: unknown;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function toError(response: Response): Promise<ApiError> {
  let code = "http_error";
  let message = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      return new ApiError(response.status, code, message, body.error.details);
    }
  } catch {
    /* non-JSON body */
  }
  return new ApiError(response.status, code, message);
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, body, signal } = options;
  const response = await fetch(buildUrl(path, query), {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (!response.ok) throw await toError(response);

  const envelope = (await response.json()) as ApiEnvelope<T>;
  return envelope.data as T;
}

/** POST to a streaming endpoint; returns the raw Response for the caller to read. */
export async function apiStream(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await fetch(buildUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await toError(response);
  return response;
}
