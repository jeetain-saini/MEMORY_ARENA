import { CheckCircle2, Circle, XCircle } from "lucide-react";

import type { AgentStepEvent } from "@/types/agent";

const STAGE_LABELS: Record<string, string> = {
  retrieve: "Retrieve memories",
  expand: "Graph expansion",
  build_context: "Build context",
  generate: "Generate answer",
};

export function TraceTimeline({
  steps,
  streaming,
}: {
  steps: AgentStepEvent[];
  streaming: boolean;
}) {
  return (
    <ol className="space-y-2">
      {steps.map((step, i) => (
        <li key={i} className="flex items-start gap-2 text-sm">
          {step.ok ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-500" />
          ) : (
            <XCircle className="mt-0.5 h-4 w-4 text-rose-500" />
          )}
          <div>
            <p className="font-medium">{STAGE_LABELS[step.step] ?? step.step}</p>
            {step.summary ? (
              <p className="text-xs text-muted-foreground">{step.summary}</p>
            ) : null}
            {step.error ? <p className="text-xs text-rose-600">{step.error}</p> : null}
          </div>
        </li>
      ))}
      {streaming ? (
        <li className="flex items-center gap-2 text-sm text-muted-foreground">
          <Circle className="h-4 w-4 animate-pulse" />
          working…
        </li>
      ) : null}
    </ol>
  );
}
