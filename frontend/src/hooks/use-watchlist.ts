"use client";

/**
 * @deprecated Use `useWatchlistApi` / `useAddToWatchlist` /
 * `useRemoveFromWatchlist` from `@/hooks/use-watchlist-api` instead.
 *
 * This localStorage-backed hook is the LEGACY watchlist storage. The
 * authoritative source of truth is now the API (`/api/v1/watchlist`)
 * as of Round 5.x. /portfolio runs a one-shot migration on mount via
 * `migrateLocalWatchlistToApi()` in `@/lib/watchlist-migration` to copy
 * any remaining localStorage entries up to the server, then clears the
 * `uni-seeker-watchlist` key.
 *
 * This hook is still imported by:
 *   - `src/app/page.tsx` (home page)
 *   - `src/app/stocks/[symbol]/page.tsx`
 *
 * Those surfaces will be migrated to the API hook in a follow-up round.
 * Do NOT add new call sites — use the API hook for any new feature.
 */
import { useState, useCallback, useEffect } from "react";

const STORAGE_KEY = "uni-seeker-watchlist";

/** @deprecated See file-level note. */
export interface WatchlistItem {
  symbol: string;
  name: string;
  market: string;
  addedAt: string;
}

function load(): WatchlistItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function save(items: WatchlistItem[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

/** @deprecated See file-level note. Use `useWatchlistApi` instead. */
export function useWatchlist() {
  const [items, setItems] = useState<WatchlistItem[]>(load);

  useEffect(() => {
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        // Another tab updated the watchlist — sync state
        try {
          const parsed = JSON.parse(e.newValue);
          setItems(parsed);
        } catch {}
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  const add = useCallback((symbol: string, name: string, market: string) => {
    setItems((prev) => {
      if (prev.some((i) => i.symbol === symbol)) return prev;
      const next = [...prev, { symbol, name, market, addedAt: new Date().toISOString() }];
      save(next);
      return next;
    });
  }, []);

  const remove = useCallback((symbol: string) => {
    setItems((prev) => {
      const next = prev.filter((i) => i.symbol !== symbol);
      save(next);
      return next;
    });
  }, []);

  const removeMany = useCallback((symbols: Set<string>) => {
    setItems((prev) => {
      const next = prev.filter((i) => !symbols.has(i.symbol));
      save(next);
      return next;
    });
  }, []);

  const has = useCallback((symbol: string) => items.some((i) => i.symbol === symbol), [items]);

  const toggle = useCallback(
    (symbol: string, name: string, market: string) => {
      if (has(symbol)) {
        remove(symbol);
      } else {
        add(symbol, name, market);
      }
    },
    [add, remove, has],
  );

  return { items, add, remove, removeMany, has, toggle };
}
