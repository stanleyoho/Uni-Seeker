"use client";
import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { fetchMe, type AuthUser } from "@/lib/api-client";

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
    if (t) localStorage.setItem("token", t);
    else localStorage.removeItem("token");
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, [setToken]);

  useEffect(() => {
    const saved = localStorage.getItem("token");
    if (saved) {
      setTokenState(saved);
      fetchMe(saved).then(setUser).catch(() => { localStorage.removeItem("token"); }).finally(() => setLoading(false));
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
