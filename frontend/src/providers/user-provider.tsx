"use client";

// UserContext — resolves the active tenant (user_id) with priority:
//   1. localStorage override
//   2. NEXT_PUBLIC_DEFAULT_USER_ID
//   3. empty (the UI prompts for a User ID)
// Changes persist to localStorage. No auth, no users endpoint — Stage 12 only.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { USER_ID_STORAGE_KEY } from "@/lib/constants";

interface UserContextValue {
  userId: string;
  /** True once the initial (localStorage/env) resolution has run on the client. */
  ready: boolean;
  setUserId: (value: string) => void;
  clearUserId: () => void;
}

const UserContext = createContext<UserContextValue | null>(null);

const ENV_DEFAULT = process.env.NEXT_PUBLIC_DEFAULT_USER_ID ?? "";

export function UserProvider({ children }: { children: ReactNode }) {
  const [userId, setUserIdState] = useState<string>("");
  const [ready, setReady] = useState(false);

  // Resolve on mount (client-only, so SSR and CSR markup agree before hydration).
  useEffect(() => {
    let resolved = ENV_DEFAULT;
    try {
      const stored = window.localStorage.getItem(USER_ID_STORAGE_KEY);
      if (stored) resolved = stored;
    } catch {
      /* localStorage unavailable */
    }
    setUserIdState(resolved.trim());
    setReady(true);
  }, []);

  const setUserId = useCallback((value: string) => {
    const next = value.trim();
    setUserIdState(next);
    try {
      if (next) window.localStorage.setItem(USER_ID_STORAGE_KEY, next);
      else window.localStorage.removeItem(USER_ID_STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const clearUserId = useCallback(() => setUserId(""), [setUserId]);

  const value = useMemo<UserContextValue>(
    () => ({ userId, ready, setUserId, clearUserId }),
    [userId, ready, setUserId, clearUserId],
  );

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
}

export function useUserContext(): UserContextValue {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUserContext must be used within a UserProvider");
  return ctx;
}
