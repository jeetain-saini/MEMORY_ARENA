// Minimal Server-Sent-Events parser for `fetch`-based streaming.
//
// EventSource only supports GET, but `/query/stream` is a POST. So we read the
// Response body with a reader and parse `event:`/`data:` frames (separated by a
// blank line) ourselves.

import type { AgentStreamEvent } from "@/types/agent";

interface RawFrame {
  event: string;
  data: string;
}

function parseFrame(block: string): RawFrame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

/** Async-iterate parsed agent stream events from a streaming Response. */
export async function* readAgentStream(
  response: Response,
): AsyncGenerator<AgentStreamEvent> {
  const body = response.body;
  if (!body) return;
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const frame = parseFrame(block);
        if (!frame) continue;
        try {
          yield { event: frame.event, data: JSON.parse(frame.data) } as AgentStreamEvent;
        } catch {
          /* skip malformed frame */
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
