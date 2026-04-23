"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import zhTW from "./locales/zh-TW.json";
import en from "./locales/en.json";

type Locale = "zh-TW" | "en";

/* eslint-disable @typescript-eslint/no-explicit-any */
const messages: Record<Locale, Record<string, any>> = { "zh-TW": zhTW, en };

function resolve(obj: Record<string, any>, path: string): string {
  const keys = path.split(".");
  let cur: any = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== "object") return path;
    cur = cur[k];
  }
  return typeof cur === "string" ? cur : path;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>("zh-TW");
  const t = useCallback((key: string) => resolve(messages[locale], key), [locale]);

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
