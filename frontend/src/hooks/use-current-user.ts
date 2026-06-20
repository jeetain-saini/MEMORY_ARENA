"use client";

import { useUserContext } from "@/providers/user-provider";

/** Reusable accessor for the active tenant id and setters. */
export function useCurrentUser() {
  const { userId, ready, setUserId, clearUserId } = useUserContext();
  return { userId, ready, hasUser: userId.length > 0, setUserId, clearUserId };
}
