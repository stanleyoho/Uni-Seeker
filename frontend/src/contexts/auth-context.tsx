"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { fetchMe, type AuthUser } from "@/lib/api-client";

// Canonical localStorage key for the auth token. Must match the key read by
// `getAuthHeaders()` in `src/lib/api-client.ts`. The previous implementation
// wrote to "token" while the API client read from "auth_token", causing 401s
// on authenticated endpoints. The legacy "token" key is still read once on
// mount for backward compatibility (Round 6+ users) and then migrated.
const TOKEN_KEY = "auth_token";
const LEGACY_TOKEN_KEY = "token";

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  setToken: (token: string | null) => void;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType>({
  user: null, token: null, setToken: () => {}, logout: () => {}, loading: true,
});

// One-time legacy "token" -> "auth_token" migration. Runs at module
// load (client only) so the value is correct before any React render.
if (typeof window !== "undefined") {
  try {
    if (!window.localStorage.getItem(TOKEN_KEY)) {
      const legacy = window.localStorage.getItem(LEGACY_TOKEN_KEY);
      if (legacy) {
        window.localStorage.setItem(TOKEN_KEY, legacy);
        window.localStorage.removeItem(LEGACY_TOKEN_KEY);
      }
    }
  } catch {
    /* ignore quota / disabled storage */
  }
}

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function subscribeStoredToken(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  window.addEventListener("uni-seeker:auth-change", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("uni-seeker:auth-change", callback);
  };
}

// SSR snapshot is null so the initial HTML matches what the server
// renders for unauthenticated users; the client takes over on first
// render via useSyncExternalStore.
const getServerTokenSnapshot = (): string | null => null;

export function AuthProvider({ children }: { children: ReactNode }) {
  // Token is sourced from localStorage via a subscription -- avoids the
  // "setState inside useEffect to mirror localStorage" smell flagged by
  // react-hooks/set-state-in-effect.
  const token = useSyncExternalStore(
    subscribeStoredToken,
    readStoredToken,
    getServerTokenSnapshot,
  );
  const [user, setUser] = useState<AuthUser | null>(null);
  // Loading is derived: we're loading while a token exists but the
  // matching user hasn't been fetched yet. Tokenless / fetched
  // sessions both report loading=false without any setState.
  const loading = token != null && user == null;

  const setToken = useCallback((t: string | null) => {
    try {
      if (t) {
        window.localStorage.setItem(TOKEN_KEY, t);
      } else {
        window.localStorage.removeItem(TOKEN_KEY);
        // Also clear the legacy key on logout in case a stale value lingered.
        window.localStorage.removeItem(LEGACY_TOKEN_KEY);
      }
    } catch {
      /* ignore quota / disabled storage */
    }
    window.dispatchEvent(new Event("uni-seeker:auth-change"));
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, [setToken]);

  // Hydrate user from server whenever we observe a token without one.
  // setUser / setToken inside .then() are asynchronous (in a Promise
  // callback), so the react-hooks/set-state-in-effect rule -- which
  // only flags *synchronous* setState in the effect body -- does not
  // fire here.
  useEffect(() => {
    if (!token || user) return;
    let cancelled = false;
    fetchMe(token)
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) setToken(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token, user, setToken]);

  return <AuthContext.Provider value={{ user, token, setToken, logout, loading }}>{children}</AuthContext.Provider>;
}

export function useAuth() { return useContext(AuthContext); }
