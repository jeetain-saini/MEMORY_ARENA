"use client";

import { Info } from "lucide-react";
import { useMemo } from "react";

import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, LoadingRows, NoUserState } from "@/components/shared/states";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useSummaries } from "@/hooks/use-summaries";
import { SUMMARY_SCOPES } from "@/lib/constants";
import { formatDateTime } from "@/lib/utils";

export default function SummariesPage() {
  const { userId, ready, hasUser } = useCurrentUser();
  const summaries = useSummaries(userId);

  const byScope = useMemo(() => {
    const map = new Map((summaries.data ?? []).map((s) => [s.scope, s] as const));
    return map;
  }, [summaries.data]);

  if (!ready) return <LoadingRows rows={4} />;
  if (!hasUser) return <NoUserState />;

  return (
    <div>
      <PageHeader
        title="Summary Explorer"
        description="Rolling summaries for projects, goals, and experiences."
      />

      {summaries.isLoading ? (
        <LoadingRows rows={3} />
      ) : summaries.isError ? (
        // Stage 11 stores summaries but exposes no read API yet — degrade gracefully.
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center">
          <Info className="h-8 w-8 text-muted-foreground" />
          <p className="font-medium">Summaries read API not available</p>
          <p className="max-w-lg text-sm text-muted-foreground">
            Summaries are generated and stored by the Stage 11 maintenance workflow, but no
            read endpoint is exposed yet. Add a thin{" "}
            <code className="rounded bg-muted px-1">GET /api/v1/summaries/&#123;user_id&#125;</code>{" "}
            endpoint and this page will populate automatically — no frontend changes needed.
          </p>
        </div>
      ) : (
        <Tabs defaultValue={SUMMARY_SCOPES[0]}>
          <TabsList>
            {SUMMARY_SCOPES.map((scope) => (
              <TabsTrigger key={scope} value={scope} className="capitalize">
                {scope}
              </TabsTrigger>
            ))}
          </TabsList>
          {SUMMARY_SCOPES.map((scope) => {
            const summary = byScope.get(scope);
            return (
              <TabsContent key={scope} value={scope}>
                {summary ? (
                  <Card>
                    <CardHeader className="flex-row items-center justify-between pb-3">
                      <CardTitle className="text-sm capitalize">{scope} summary</CardTitle>
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">v{summary.version}</Badge>
                        <Badge variant="outline">{summary.source_count} sources</Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <pre className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-sm leading-relaxed">
                        {summary.summary_text}
                      </pre>
                      <p className="text-xs text-muted-foreground">
                        Updated {formatDateTime(summary.updated_at)}
                      </p>
                    </CardContent>
                  </Card>
                ) : (
                  <EmptyState title={`No ${scope} summary yet`} />
                )}
              </TabsContent>
            );
          })}
        </Tabs>
      )}
    </div>
  );
}
