"use client";

import {
  Bot,
  Brain,
  Database,
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
      <div className="mb-4 flex items-center gap-2 px-2">
        <Brain className="h-6 w-6 text-primary" />
        <span className="text-lg font-bold">MemoryArena</span>
      </div>
      {NAV_ITEMS.map((item) => {
        const Icon = ICONS[item.icon] ?? LayoutDashboard;
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            {item.label}
          </Link>
        );
      })}
      <div className="mt-auto px-3 pt-4 text-xs text-muted-foreground">
        Stage 12 · Dashboard
      </div>
    </nav>
  );
}
