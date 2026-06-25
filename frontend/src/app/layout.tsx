import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/providers/query-provider";
import { UserProvider } from "@/providers/user-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "MemoryArena Dashboard",
  description: "Explore, query, and inspect MemoryArena memories.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="relative min-h-screen bg-background text-foreground antialiased">
        {/* Ambient premium backdrop: soft indigo glows on near-black. */}
        <div
          aria-hidden
          className="pointer-events-none fixed inset-0 -z-10"
          style={{
            backgroundImage:
              "radial-gradient(60% 50% at 15% 0%, rgba(99,102,241,0.12), transparent 60%), radial-gradient(50% 50% at 100% 0%, rgba(139,92,246,0.10), transparent 55%), radial-gradient(60% 60% at 50% 120%, rgba(56,189,248,0.06), transparent 60%)",
          }}
        />
        <QueryProvider>
          <UserProvider>
            <AppShell>{children}</AppShell>
            <Toaster richColors position="top-right" />
          </UserProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
