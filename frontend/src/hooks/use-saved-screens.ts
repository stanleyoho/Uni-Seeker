"use client";

import { useState, useCallback } from "react";
import type { ScreenCondition } from "@/lib/api-client";

const STORAGE_KEY = "uni-seeker-saved-screens";

export interface SavedScreen {
  id: string;
  name: string;
  conditions: ScreenCondition[];
  operator: "AND" | "OR";
  createdAt: string;
}

function load(): SavedScreen[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function persist(items: SavedScreen[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

export function useSavedScreens() {
  const [items, setItems] = useState<SavedScreen[]>(load);

  const save = useCallback((name: string, conditions: ScreenCondition[], operator: "AND" | "OR") => {
    setItems((prev) => {
      const next = [
        ...prev,
        {
          id: Date.now().toString(36),
          name,
          conditions,
          operator,
          createdAt: new Date().toISOString(),
        },
      ];
      persist(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setItems((prev) => {
      const next = prev.filter((s) => s.id !== id);
      persist(next);
      return next;
    });
  }, []);

  return { items, save, remove };
}
