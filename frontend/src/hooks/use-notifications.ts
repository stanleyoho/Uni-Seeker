"use client";

import { useState, useEffect, useCallback } from "react";
import { type ScreenCondition } from "@/lib/api-client";

const STORAGE_KEY = "uni-seeker-alert-rules";

export interface AlertRule {
  id: string;
  name: string;
  conditions: ScreenCondition[];
  is_active: boolean;
}

function loadRules(): AlertRule[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveRules(rules: AlertRule[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rules));
}

export function useNotifications() {
  const [rules, setRules] = useState<AlertRule[]>([]);

  useEffect(() => {
    setRules(loadRules());
  }, []);

  const addRule = useCallback((rule: AlertRule) => {
    setRules((prev) => {
      const next = [...prev, rule];
      saveRules(next);
      return next;
    });
  }, []);

  const removeRule = useCallback((id: string) => {
    setRules((prev) => {
      const next = prev.filter((r) => r.id !== id);
      saveRules(next);
      return next;
    });
  }, []);

  const toggleRule = useCallback((id: string) => {
    setRules((prev) => {
      const next = prev.map((r) =>
        r.id === id ? { ...r, is_active: !r.is_active } : r
      );
      saveRules(next);
      return next;
    });
  }, []);

  return { rules, addRule, removeRule, toggleRule };
}
