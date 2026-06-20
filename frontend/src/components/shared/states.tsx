import { AlertCircle, Inbox, UserCog } from "lucide-react";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export function LoadingRows({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
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
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-10 text-center">
      {icon}
      <p className="font-medium">{title}</p>
      {description ? (
        <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      ) : null}
      {children}
    </div>
  );
}

export function EmptyState({ title, description, children }: Omit<PanelProps, "icon">) {
  return (
    <Panel
      icon={<Inbox className="h-8 w-8 text-muted-foreground" />}
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
      icon={<AlertCircle className="h-8 w-8 text-destructive" />}
      title="Request failed"
      description={message}
    />
  );
}

export function NoUserState() {
  return (
    <Panel
      icon={<UserCog className="h-8 w-8 text-muted-foreground" />}
      title="No User ID set"
      description="Enter a User ID in the top bar (or set NEXT_PUBLIC_DEFAULT_USER_ID) to load this tenant's memories."
    />
  );
}
