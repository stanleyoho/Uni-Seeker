"use client";

import { useState, useCallback } from "react";

const STORAGE_KEY = "uni-seeker-watchlist";

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

export function useWatchlist() {
  const [items, setItems] = useState<WatchlistItem[]>(load);

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

  return { items, add, remove, has, toggle };
}
