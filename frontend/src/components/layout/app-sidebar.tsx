"use client";

import {
  Bot,
  Brain,
  Database,
  History,
  Layers,
  LayoutDashboard,
  ScrollText,
  Share2,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV_ITEMS } from "@/lib/constants";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  LayoutDashboard,
  History,
  Database,
  Share2,
  Layers,
  Bot,
  ScrollText,
};

export function AppSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex h-full flex-col gap-1 p-3">
      <Link
        href="/"
        onClick={onNavigate}
        className="mb-5 flex items-center gap-2.5 px-2 pt-1"
        aria-label="MemoryArena home"
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary shadow-lg shadow-primary/20">
          <Brain className="h-5 w-5 text-foreground" />
        </span>
        <span className="text-lg font-semibold tracking-tight text-foreground">MemoryArena</span>
      </Link>
      {NAV_ITEMS.map((item) => {
        const Icon = ICONS[item.icon] ?? LayoutDashboard;
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
              active
                ? "border border-border bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            {active ? (
              <span className="absolute left-0 top-1/2 h-5 -translate-y-1/2 rounded-full bg-gradient-to-b from-primary to-primary [width:3px]" />
            ) : null}
            <Icon
              className={cn(
                "h-4 w-4 transition-colors",
                active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
              )}
            />
            {item.label}
          </Link>
        );
      })}
      <div className="mt-auto px-3 pt-4 text-xs text-muted-foreground/70">
        MemoryArena · Premium
      </div>
    </nav>
  );
}
