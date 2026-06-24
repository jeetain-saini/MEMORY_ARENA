"use client";

import { useEffect } from "react";

/**
 * Route-segment error boundary (Next.js App Router). Catches render/runtime
 * errors thrown anywhere in a page subtree so a single broken component shows a
 * recoverable fallback instead of a blank screen. Rendered inside the root
 * layout, so the app shell/navigation remain usable.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface for debugging; a production deploy would forward this to an error
    // tracker (Sentry, etc.).
    console.error("Route error boundary caught:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <h2 className="text-lg font-semibold text-foreground">Something went wrong</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        This page hit an unexpected error. You can retry, or switch to another section
        from the navigation.
        {error?.digest ? (
          <span className="mt-2 block font-mono text-xs opacity-60">ref: {error.digest}</span>
        ) : null}
      </p>
      <button
        type="button"
        onClick={() => reset()}
        className="rounded-md border border-border px-4 py-2 text-sm font-medium transition hover:bg-accent"
      >
        Try again
      </button>
    </div>
  );
}
