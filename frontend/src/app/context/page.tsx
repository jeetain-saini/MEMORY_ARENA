"use client";

import { Play } from "lucide-react";
import { useState } from "react";

import { CompressionView, ContextPackageView } from "@/components/context/context-views";
import { RetrievalResults } from "@/components/context/retrieval-results";
import { JsonViewer } from "@/components/shared/json-viewer";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState, LoadingRows, NoUserState } from "@/components/shared/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useContextDebug } from "@/hooks/use-context";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useRetrievalDebug } from "@/hooks/use-retrieval";

export default function ContextPage() {
  const { userId, ready, hasUser } = useCurrentUser();
  const [query, setQuery] = useState("");
  const [maxTokens, setMaxTokens] = useState(2000);
  const [topK, setTopK] = useState(20);

  const context = useContextDebug();
  const retrieval = useRetrievalDebug();

  const run = () => {
    if (!query.trim()) return;
    context.mutate({ query, user_id: userId, max_tokens: maxTokens, top_k: topK });
    retrieval.mutate({ query, user_id: userId, top_k: topK });
  };

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  const pending = context.isPending || retrieval.isPending;
  const hasRun = context.data || retrieval.data || context.isError;

  return (
    <div>
      <PageHeader
        title="Context Playground"
        description="Submit a query and inspect retrieval, the assembled context package, and compression."
      />

      <div className="space-y-3 rounded-lg border bg-card p-4">
        <Textarea
          placeholder="Enter a query to assemble context for…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={2}
        />
        <div className="flex flex-wrap items-end gap-4">
          <label className="text-xs text-muted-foreground">
            max_tokens
            <Input
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
              className="mt-1 w-28"
            />
          </label>
          <label className="text-xs text-muted-foreground">
            top_k
            <Input
              type="number"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="mt-1 w-24"
            />
          </label>
          <Button onClick={run} disabled={pending || !query.trim()} className="ml-auto">
            <Play className="h-4 w-4" /> {pending ? "Building…" : "Build context"}
          </Button>
        </div>
      </div>

      <div className="mt-6">
        {!hasRun ? (
          <EmptyState title="Run a query" description="Results appear here across four tabs." />
        ) : (
          <Tabs defaultValue="context">
            <TabsList>
              <TabsTrigger value="retrieval">Retrieval</TabsTrigger>
              <TabsTrigger value="context">Context</TabsTrigger>
              <TabsTrigger value="compression">Compression</TabsTrigger>
              <TabsTrigger value="raw">Raw</TabsTrigger>
            </TabsList>

            <TabsContent value="retrieval">
              {retrieval.isPending ? (
                <LoadingRows rows={4} />
              ) : retrieval.data ? (
                retrieval.data.results.length ? (
                  <RetrievalResults results={retrieval.data.results} />
                ) : (
                  <EmptyState title="No retrieval hits" />
                )
              ) : (
                <ErrorState error={retrieval.error} />
              )}
            </TabsContent>

            <TabsContent value="context">
              {context.isPending ? (
                <LoadingRows rows={4} />
              ) : context.data ? (
                <ContextPackageView debug={context.data} />
              ) : (
                <ErrorState error={context.error} />
              )}
            </TabsContent>

            <TabsContent value="compression">
              {context.data ? (
                <CompressionView debug={context.data} />
              ) : context.isPending ? (
                <LoadingRows rows={2} />
              ) : (
                <ErrorState error={context.error} />
              )}
            </TabsContent>

            <TabsContent value="raw">
              <JsonViewer value={{ context: context.data, retrieval: retrieval.data }} />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </div>
  );
}
