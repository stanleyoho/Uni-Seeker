"use client";

import { useI18n } from "@/i18n/context";
import { useMemo } from "react";

export function useLocaleFormat() {
  const { locale } = useI18n();

  return useMemo(() => ({
    formatNumber: (value: number, options?: Intl.NumberFormatOptions) => {
      return new Intl.NumberFormat(locale === "zh-TW" ? "zh-TW" : "en-US", options).format(value);
    },
    formatPercent: (value: number, decimals = 2) => {
      return new Intl.NumberFormat(locale === "zh-TW" ? "zh-TW" : "en-US", {
        style: "percent",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(value / 100);
    },
    formatCurrency: (value: number, currency = "TWD") => {
      return new Intl.NumberFormat(locale === "zh-TW" ? "zh-TW" : "en-US", {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(value);
    },
    formatDate: (dateStr: string) => {
      const date = new Date(dateStr);
      return new Intl.DateTimeFormat(locale === "zh-TW" ? "zh-TW" : "en-US", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(date);
    },
    formatDateTime: (dateStr: string) => {
      const date = new Date(dateStr);
      return new Intl.DateTimeFormat(locale === "zh-TW" ? "zh-TW" : "en-US", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    },
  }), [locale]);
}
