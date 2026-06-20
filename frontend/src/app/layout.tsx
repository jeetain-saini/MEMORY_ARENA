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
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background antialiased">
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
