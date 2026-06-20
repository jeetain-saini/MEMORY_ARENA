"use client";

import { Check, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentUser } from "@/hooks/use-current-user";
import { isUuidLike } from "@/lib/utils";

/** Editable User ID field (top bar). Persists to localStorage via UserContext. */
export function UserIdField() {
  const { userId, setUserId } = useCurrentUser();
  const [draft, setDraft] = useState(userId);

  useEffect(() => setDraft(userId), [userId]);

  const dirty = draft.trim() !== userId;
  const valid = draft.trim() === "" || isUuidLike(draft);

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) setUserId(draft);
      }}
    >
      <div className="relative">
        <UserRound className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          aria-label="User ID"
          placeholder="User ID (UUID)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-[16rem] pl-8 font-mono text-xs"
        />
      </div>
      <Button
        type="submit"
        size="sm"
        variant={dirty ? "default" : "secondary"}
        disabled={!dirty || !valid}
        title={!valid ? "Enter a valid UUID" : "Apply user"}
      >
        <Check className="h-4 w-4" />
        Apply
      </Button>
    </form>
  );
}
