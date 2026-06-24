"use client";

import { useEffect } from "react";

/**
 * Root error boundary (Next.js App Router). Catches errors thrown in the root
 * layout itself — where the per-route error.tsx cannot help — so the app never
 * white-screens. It must render its own <html>/<body> because it replaces the
 * root layout when active.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global error boundary caught:", error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-background antialiased">
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
          <h2 className="text-lg font-semibold text-foreground">Application error</h2>
          <p className="max-w-md text-sm text-muted-foreground">
            The application encountered a fatal error and could not render. Please reload.
          </p>
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium transition hover:bg-accent"
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
