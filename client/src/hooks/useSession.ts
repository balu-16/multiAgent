"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage, SESSION_EXPIRED_EVENT } from "@/lib/api";
import type { User } from "@/types/chat";

type SessionState =
  | { status: "restoring"; user: null; error: null }
  | { status: "signed_out"; user: null; error: string | null }
  | { status: "unavailable"; user: null; error: string }
  | { status: "authenticated"; user: User; error: null };

export function useSession() {
  const [session, setSession] = useState<SessionState>({ status: "restoring", user: null, error: null });
  const [restoreVersion, setRestoreVersion] = useState(0);
  const generation = useRef(0);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    setSession({ status: "restoring", user: null, error: null });
    api.me(controller.signal).then(({ user }) => {
      if (current === generation.current && !controller.signal.aborted) setSession({ status: "authenticated", user, error: null });
    }).catch((error: unknown) => {
      if (current !== generation.current || controller.signal.aborted) return;
      setSession(error instanceof ApiError && error.status === 401
        ? { status: "signed_out", user: null, error: null }
        : { status: "unavailable", user: null, error: errorMessage(error) });
    });
    return () => { controller.abort(); };
  }, [restoreVersion]);

  useEffect(() => {
    function expire() {
      generation.current += 1;
      setExpired(true);
      setSession({ status: "signed_out", user: null, error: "Your session ended. Sign in again to continue." });
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
  }, []);

  const acceptUser = useCallback((user: User) => {
    generation.current += 1;
    setExpired(false);
    setSession({ status: "authenticated", user, error: null });
  }, []);
  const logout = useCallback(async () => {
    await api.logout();
    generation.current += 1;
    setExpired(false);
    setSession({ status: "signed_out", user: null, error: null });
  }, []);
  const restore = useCallback(() => setRestoreVersion((value) => value + 1), []);
  return { ...session, expired, acceptUser, logout, restore, generation };
}
