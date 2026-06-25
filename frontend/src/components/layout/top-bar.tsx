"use client";

import { Menu } from "lucide-react";

import { UserIdField } from "@/components/layout/user-id-field";
import { Button } from "@/components/ui/button";

export function TopBar({ onMenu }: { onMenu?: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/70 px-4 ">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onMenu}
        aria-label="Toggle navigation"
      >
        <Menu className="h-5 w-5" />
      </Button>
      <div className="font-semibold tracking-tight md:hidden">MemoryArena</div>
      <div className="ml-auto">
        <UserIdField />
      </div>
    </header>
  );
}
