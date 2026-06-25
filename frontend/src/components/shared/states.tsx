import { AlertCircle, Inbox, UserCog } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function LoadingRows({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="relative h-16 w-full overflow-hidden rounded-xl border border-border bg-card"
        >
          <span className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-foreground/5 to-transparent" />
        </div>
      ))}
    </div>
  );
}

interface PanelProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  children?: ReactNode;
}

function Panel({ icon, title, description, children }: PanelProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-card p-12 text-center ">
      {icon ? (
        <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-card">
          {icon}
        </div>
      ) : null}
      <p className="font-medium text-foreground">{title}</p>
      {description ? (
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p>
      ) : null}
      {children}
    </div>
  );
}

export function EmptyState({ title, description, children }: Omit<PanelProps, "icon">) {
  return (
    <Panel
      icon={<Inbox className="h-6 w-6 text-muted-foreground" />}
      title={title}
      description={description}
    >
      {children}
    </Panel>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <Panel
      icon={<AlertCircle className="h-6 w-6 text-destructive" />}
      title="Request failed"
      description={message}
    />
  );
}

export function NoUserState() {
  return (
    <Panel
      icon={<UserCog className="h-6 w-6 text-muted-foreground" />}
      title="No User ID set"
      description="Enter a User ID in the top bar (or set NEXT_PUBLIC_DEFAULT_USER_ID) to load this tenant's memories."
    />
  );
}
