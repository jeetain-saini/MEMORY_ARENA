"use client";

import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { TopBar } from "@/components/layout/top-bar";
import { cn } from "@/lib/utils";

// Routes that render full-bleed, without the app sidebar/top bar chrome.
const CHROMELESS_ROUTES = new Set<string>(["/"]);

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  // The marketing landing page owns the full viewport (its own fixed nav).
  if (CHROMELESS_ROUTES.has(pathname)) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen w-full">
      {/* Desktop sidebar — glass rail */}
      <aside className="hidden w-64 shrink-0 border-r border-white/10 bg-white/[0.02] backdrop-blur-xl md:block">
        <div className="sticky top-0 h-screen">
          <AppSidebar />
        </div>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <aside className="absolute left-0 top-0 h-full w-64 border-r border-white/10 bg-background/95 backdrop-blur-xl">
            <AppSidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setMobileOpen(true)} />
        {/* `key` re-triggers the entrance animation on route change. */}
        <main key={pathname} className={cn("page-enter mx-auto w-full max-w-7xl flex-1 p-4 md:p-8")}>
          {children}
        </main>
      </div>
    </div>
  );
}
