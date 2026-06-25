"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Send, Square } from "lucide-react";
import { useState } from "react";

import { SourceAttribution } from "@/components/agent/source-attribution";
import { TraceTimeline } from "@/components/agent/trace-timeline";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, LoadingRows, NoUserState } from "@/components/shared/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useAgentStream } from "@/hooks/use-agent-stream";
import { useCurrentUser } from "@/hooks/use-current-user";

export default function AgentPage() {
  const { userId, ready, hasUser } = useCurrentUser();
  const [query, setQuery] = useState("");
  const { state, run, cancel, reset } = useAgentStream();
  const queryClient = useQueryClient();

  // An agent turn captures the user's message into a memory server-side, but the
  // ingestion runs asynchronously off the request path — so the /memories,
  // /graph, /summaries, and analytics caches are stale after a turn. Once the
  // turn finishes, wait for the background capture to land, then invalidate
  // those caches so the new memory shows up everywhere without a manual refresh.
  const ask = async (text: string) => {
    await run(userId, text);
    window.setTimeout(() => {
      for (const key of ["memories", "analytics", "graph", "summaries"]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    }, 4000);
  };

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  const streaming = state.status === "streaming";

  return (
    <div>
      <PageHeader
        title="Agent Playground"
        description="Query the memory agent and watch retrieval → expansion → context → answer stream."
      />

      <div className="space-y-3 rounded-lg border bg-card p-4">
        <Textarea
          placeholder="Ask the agent a question…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(query);
          }}
        />
        <div className="flex items-center gap-2">
          {streaming ? (
            <Button variant="destructive" onClick={cancel}>
              <Square className="h-4 w-4" /> Stop
            </Button>
          ) : (
            <Button onClick={() => ask(query)} disabled={!query.trim()}>
              <Send className="h-4 w-4" /> Ask agent
            </Button>
          )}
          {state.status !== "idle" ? (
            <Button variant="ghost" onClick={reset}>
              Clear
            </Button>
          ) : null}
          <span className="ml-auto text-xs text-muted-foreground">⌘/Ctrl + Enter to send</span>
        </div>
      </div>

      {state.status === "idle" ? (
        <div className="mt-6">
          <EmptyState title="Ask a question" description="The execution trace and answer stream in live." />
        </div>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_18rem]">
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex-row items-center justify-between pb-3">
                <CardTitle className="text-sm">Answer</CardTitle>
                {state.finishReason ? (
                  <Badge variant={state.status === "error" ? "destructive" : "secondary"}>
                    {state.finishReason}
                  </Badge>
                ) : null}
              </CardHeader>
              <CardContent>
                {state.error ? (
                  <p className="text-sm text-rose-600">{state.error}</p>
                ) : state.answer ? (
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{state.answer}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {streaming ? "Generating…" : "No answer."}
                  </p>
                )}
              </CardContent>
            </Card>

            <SourceAttribution citations={state.citations} />
          </div>

          <Card className="h-fit">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Execution trace</CardTitle>
            </CardHeader>
            <CardContent>
              <TraceTimeline steps={state.steps} streaming={streaming} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
