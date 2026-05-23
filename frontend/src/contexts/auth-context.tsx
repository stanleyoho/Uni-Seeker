"use client";
import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const setToken = useCallback((t: string | null) => {
    setTokenState(t);
    if (t) {
      localStorage.setItem(TOKEN_KEY, t);
    } else {
      localStorage.removeItem(TOKEN_KEY);
      // Also clear the legacy key on logout in case a stale value lingered.
      localStorage.removeItem(LEGACY_TOKEN_KEY);
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, [setToken]);

  useEffect(() => {
    // Read canonical key first; fall back to legacy "token" for users who
    // logged in before the key was unified. If a legacy value is found,
    // migrate it to the canonical key and drop the legacy entry.
    let saved = localStorage.getItem(TOKEN_KEY);
    if (!saved) {
      const legacy = localStorage.getItem(LEGACY_TOKEN_KEY);
      if (legacy) {
        localStorage.setItem(TOKEN_KEY, legacy);
        localStorage.removeItem(LEGACY_TOKEN_KEY);
        saved = legacy;
      }
    }
    if (saved) {
      setTokenState(saved);
      fetchMe(saved).then(setUser).catch(() => { localStorage.removeItem(TOKEN_KEY); }).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token && !user) {
      fetchMe(token).then(setUser).catch(() => setToken(null));
    }
  }, [token, user, setToken]);

  return <AuthContext.Provider value={{ user, token, setToken, logout, loading }}>{children}</AuthContext.Provider>;
}

export function useAuth() { return useContext(AuthContext); }
