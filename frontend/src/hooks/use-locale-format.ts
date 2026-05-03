"use client";

import { useI18n } from "@/i18n/context";
import { useMemo } from "react";

export function useLocaleFormat() {
  const { locale } = useI18n();

  return useMemo(() => ({
    formatNumber: (value: number | string, options?: Intl.NumberFormatOptions) => {
      const num = typeof value === "string" ? parseFloat(value) : value;
      if (isNaN(num)) return "-";
      return new Intl.NumberFormat(locale === "zh-TW" ? "zh-TW" : "en-US", options).format(num);
    },
    formatPercent: (value: number | string, decimals = 2) => {
      const num = typeof value === "string" ? parseFloat(value) : value;
      if (isNaN(num)) return "-";
      return new Intl.NumberFormat(locale === "zh-TW" ? "zh-TW" : "en-US", {
        style: "percent",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(num / 100);
    },
    formatCurrency: (value: number | string, currency = "TWD") => {
      const num = typeof value === "string" ? parseFloat(value) : value;
      if (isNaN(num)) return "-";
      return new Intl.NumberFormat(locale === "zh-TW" ? "zh-TW" : "en-US", {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(num);
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
