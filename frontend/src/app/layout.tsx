import type { Metadata } from "next";
import { Space_Grotesk, Space_Mono } from "next/font/google";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Toaster } from "@/components/ui/sonner";
import { QueryProvider } from "@/providers/query-provider";
import { UserProvider } from "@/providers/user-provider";

import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-grotesk",
  display: "swap",
});
const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MemoryArena Dashboard",
  description: "Explore, query, and inspect MemoryArena memories.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${spaceGrotesk.variable} ${spaceMono.variable} relative min-h-screen bg-background text-foreground antialiased`}
      >
        {/* Ambient backdrop: a single, very subtle warm teal tint. */}
        <div
          aria-hidden
          className="pointer-events-none fixed inset-0 -z-10"
          style={{
            backgroundImage:
              "radial-gradient(70% 50% at 50% 0%, rgba(63,125,116,0.05), transparent 65%)",
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
