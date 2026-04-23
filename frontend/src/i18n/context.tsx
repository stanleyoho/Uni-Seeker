"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import zhTW from "./locales/zh-TW.json";
import en from "./locales/en.json";

type Locale = "zh-TW" | "en";
type Translations = typeof zhTW;

const translations: Record<Locale, Translations> = { "zh-TW": zhTW, en };

interface I18nContextType {
  locale: Locale;
  t: Translations;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nContextType>({
  locale: "zh-TW",
  t: zhTW,
  setLocale: () => {},
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("locale") as Locale) || "zh-TW";
    }
    return "zh-TW";
  });

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    if (typeof window !== "undefined") {
      localStorage.setItem("locale", newLocale);
    }
  }, []);

  return (
    <I18nContext.Provider value={{ locale, t: translations[locale], setLocale }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
