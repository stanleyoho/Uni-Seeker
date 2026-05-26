"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
} from "react";

type Theme = "dark" | "light" | "system";

interface ThemeContextValue {
  theme: Theme;
  resolvedTheme: "dark" | "light";
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "dark",
  resolvedTheme: "dark",
  setTheme: () => {},
});

const THEME_STORAGE_KEY = "uni-seeker-theme";

function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY) as Theme | null;
    return saved ?? "dark";
  } catch {
    return "dark";
  }
}

// Subscribe to other tabs writing the same key (and to our own
// programmatic writes via the synthetic event below).
function subscribeStoredTheme(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  window.addEventListener("uni-seeker:theme-change", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("uni-seeker:theme-change", callback);
  };
}

// Server snapshot must match the SSR-rendered HTML to avoid hydration
// mismatch; the user's saved preference is only applied after the first
// client-only re-render that `useSyncExternalStore` triggers.
function getServerSnapshot(): Theme {
  return "dark";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // useSyncExternalStore replaces "setState-in-effect to pull from
  // localStorage" with a single subscription, which is the official
  // React 19 recommendation cited in the
  // react-hooks/set-state-in-effect docs.
  const theme = useSyncExternalStore(
    subscribeStoredTheme,
    readStoredTheme,
    getServerSnapshot,
  );
  const [resolvedTheme, setResolvedTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    // Resolve system theme
    const resolve = () => {
      if (theme === "system") {
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        setResolvedTheme(prefersDark ? "dark" : "light");
      } else {
        setResolvedTheme(theme);
      }
    };
    resolve();

    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", resolve);
      return () => mq.removeEventListener("change", resolve);
    }
  }, [theme]);

  useEffect(() => {
    // Apply theme to document
    document.documentElement.setAttribute("data-theme", resolvedTheme);
  }, [resolvedTheme]);

  const setTheme = useCallback((t: Theme) => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, t);
    } catch {
      /* localStorage may be unavailable in private mode */
    }
    // Notify our own subscribeStoredTheme listeners (the native
    // `storage` event only fires for *other* tabs).
    window.dispatchEvent(new Event("uni-seeker:theme-change"));
  }, []);

  return (
    <ThemeContext value={{ theme, resolvedTheme, setTheme }}>
      {children}
    </ThemeContext>
  );
}

export const useTheme = () => useContext(ThemeContext);
