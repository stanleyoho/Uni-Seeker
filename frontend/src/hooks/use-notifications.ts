"use client";

import { useCallback, useSyncExternalStore } from "react";
import { type ScreenCondition } from "@/lib/api-client";

const STORAGE_KEY = "uni-seeker-alert-rules";
const CHANGE_EVENT = "uni-seeker:alert-rules-change";

export interface AlertRule {
  id: string;
  name: string;
  conditions: ScreenCondition[];
  is_active: boolean;
}

const EMPTY_RULES: AlertRule[] = [];

// useSyncExternalStore requires getSnapshot to return a referentially
// stable value when the underlying data hasn't changed; otherwise React
// will spin in an infinite re-render loop. Cache the parsed result
// against the raw localStorage string.
let cachedRaw: string | null = null;
let cachedRules: AlertRule[] = EMPTY_RULES;

function readRules(): AlertRule[] {
  if (typeof window === "undefined") return EMPTY_RULES;
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return EMPTY_RULES;
  }
  if (raw === cachedRaw) return cachedRules;
  cachedRaw = raw;
  if (!raw) {
    cachedRules = EMPTY_RULES;
    return cachedRules;
  }
  try {
    cachedRules = JSON.parse(raw) as AlertRule[];
  } catch {
    cachedRules = EMPTY_RULES;
  }
  return cachedRules;
}

function subscribeRules(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  window.addEventListener(CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(CHANGE_EVENT, callback);
  };
}

const getServerSnapshot = (): AlertRule[] => EMPTY_RULES;

function writeRules(rules: AlertRule[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rules));
  } catch {
    /* quota / private mode */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function useNotifications() {
  // Drive `rules` from a localStorage subscription rather than
  // setState-in-effect bootstrap (avoids react-hooks/set-state-in-effect).
  const rules = useSyncExternalStore(
    subscribeRules,
    readRules,
    getServerSnapshot,
  );

  const addRule = useCallback((rule: AlertRule) => {
    writeRules([...readRules(), rule]);
  }, []);

  const removeRule = useCallback((id: string) => {
    writeRules(readRules().filter((r) => r.id !== id));
  }, []);

  const toggleRule = useCallback((id: string) => {
    writeRules(
      readRules().map((r) =>
        r.id === id ? { ...r, is_active: !r.is_active } : r,
      ),
    );
  }, []);

  return { rules, addRule, removeRule, toggleRule };
}
