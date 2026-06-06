"use client";

/**
 * K4 婆媽 portfolio widgets — two oversized, glanceable summary tiles
 * pinned to the top of the /holdings page for non-technical (婆媽) users:
 *
 *   1. 今日盈虧 (Today's P&L) — reuses the summary endpoint's
 *      `total_daily_change` (NO new backend). Colored with the Taiwan
 *      紅漲綠跌 convention via `pnlColor` / `pnlDirection`
 *      (--stock-up #EE3F2C up / --stock-down #10B981 down).
 *   2. 本月股息收入 (Dividends This Month) — CASH-only cash actually
 *      received this calendar month (pay_date → fallback ex_dividend_date
 *      basis), from `/holdings/dividends/monthly-summary`. STOCK 配股 is
 *      excluded from the money figure; an optional "另有配股 N 筆" line
 *      surfaces the count when non-zero.
 *
 * Pure presentational + own data hook. Skeletons render while loading so
 * the layout never jumps. STRATOS dark-luxe glass styling reused from the
 * KPI row's skeleton chrome.
 */

import React from "react";
import { useI18n } from "@/i18n/context";
import {
  isMultiCurrencyHoldingSummary,
  type HoldingSummary,
  type MultiCurrencyHoldingSummary,
  type Currency,
} from "@/lib/api-client";
import { useMonthlyDividendSummary } from "@/hooks/use-holdings";
import { CURRENCY_SYMBOL } from "./currency-switcher";
import { toNumber, fmt, fmtSigned, pnlColor, pnlDirection } from "./types";

export interface PopoSummaryWidgetsProps {
  summary: HoldingSummary | MultiCurrencyHoldingSummary | undefined;
  summaryLoading?: boolean;
  /** Currency symbol prefix; defaults to TWD when omitted. */
  displayCurrency?: Currency;
}

/* ------------------------------------------------------------------ */
/*  Shared glass tile chrome (matches KPI skeleton/card styling)       */
/* ------------------------------------------------------------------ */

const tileStyle: React.CSSProperties = {
  background: "var(--glass-bg)",
  backdropFilter: "var(--glass-blur)",
  WebkitBackdropFilter: "var(--glass-blur)",
  border: "1px solid var(--border-color)",
  backgroundImage: "var(--glass-gradient)",
  boxShadow: "var(--glass-shadow)",
  borderRadius: "var(--glass-radius, 0)",
  padding: 24,
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const labelStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--text-secondary)",
};

const valueStyle: React.CSSProperties = {
  fontWeight: 700,
  fontVariantNumeric: "tabular-nums",
  lineHeight: 1.05,
};

function WidgetSkeleton() {
  return (
    <div style={tileStyle} aria-hidden="true">
      <div style={{ width: "45%", height: 13, background: "var(--card-hover)" }} />
      <div style={{ width: "70%", height: 40, background: "var(--card-hover)" }} />
      <div style={{ width: "35%", height: 13, background: "var(--card-hover)" }} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  i18n helpers — nested `t.holdings.popo.*` with safe fallbacks      */
/* ------------------------------------------------------------------ */

type PopoStrings = {
  today_pnl_title?: string;
  today_pnl_hint?: string;
  monthly_dividend_title?: string;
  monthly_dividend_hint?: string;
  monthly_dividend_gross?: string;
  monthly_dividend_cash_count?: string;
  monthly_dividend_stock_count?: string;
  empty_value?: string;
};

const FALLBACK: Required<PopoStrings> = {
  today_pnl_title: "今日盈虧",
  today_pnl_hint: "今日持倉市值變動",
  monthly_dividend_title: "本月股息收入",
  monthly_dividend_hint: "本月實收現金股利（淨額）",
  monthly_dividend_gross: "毛額 {amount}",
  monthly_dividend_cash_count: "{count} 筆現金股利",
  monthly_dividend_stock_count: "另有配股 {count} 筆",
  empty_value: "—",
};

function interpolate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? `{${k}}`);
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export function PopoSummaryWidgets({
  summary,
  summaryLoading = false,
  displayCurrency,
}: PopoSummaryWidgetsProps) {
  const { t } = useI18n();
  const { data: monthly, isLoading: monthlyLoading } =
    useMonthlyDividendSummary();

  const popo: Required<PopoStrings> = {
    ...FALLBACK,
    ...(((t.holdings as { popo?: PopoStrings } | undefined)?.popo) ?? {}),
  };

  // Currency symbol — prefer explicit prop, else multi-currency base, else TWD.
  const baseCcy: Currency =
    displayCurrency ??
    (summary && isMultiCurrencyHoldingSummary(summary)
      ? ((summary.base_currency as Currency) ?? "TWD")
      : "TWD");
  const symbol = CURRENCY_SYMBOL[baseCcy] ?? "";

  const gridStyle: React.CSSProperties = { display: "grid", gap: 12 };
  const gridClass = "grid-cols-1 sm:grid-cols-2";

  /* ----- Widget 1: 今日盈虧 (reuses summary.total_daily_change) ----- */
  let todayPnlNode: React.ReactNode;
  if (summaryLoading || !summary) {
    todayPnlNode = <WidgetSkeleton />;
  } else {
    const dailyChange = toNumber(summary.total_daily_change) ?? 0;
    const totalValue = toNumber(summary.total_value) ?? 0;
    const pctStr =
      totalValue > 0
        ? `${((dailyChange / totalValue) * 100).toFixed(2)}%`
        : popo.empty_value;
    const color = pnlColor(dailyChange);
    const dir = pnlDirection(dailyChange);
    const arrow = dir === "up" ? "▲" : dir === "down" ? "▼" : "";
    todayPnlNode = (
      <div style={tileStyle} data-testid="popo-today-pnl">
        <div style={labelStyle}>{popo.today_pnl_title}</div>
        <div
          className="text-[28px] lg:text-[40px]"
          style={{ ...valueStyle, color }}
        >
          {symbol} {fmtSigned(dailyChange, 0)}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color }}>
          {arrow ? `${arrow} ` : ""}
          {pctStr}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {popo.today_pnl_hint}
        </div>
      </div>
    );
  }

  /* ----- Widget 2: 本月股息收入 (monthly-summary, CASH only) ----- */
  let dividendNode: React.ReactNode;
  if (monthlyLoading || !monthly) {
    dividendNode = <WidgetSkeleton />;
  } else {
    const net = toNumber(monthly.net_amount) ?? 0;
    const gross = toNumber(monthly.gross_amount) ?? 0;
    const cashCount = monthly.cash_count ?? 0;
    const stockCount = monthly.stock_count ?? 0;
    dividendNode = (
      <div style={tileStyle} data-testid="popo-monthly-dividend">
        <div style={labelStyle}>{popo.monthly_dividend_title}</div>
        <div
          className="text-[28px] lg:text-[40px]"
          style={{ ...valueStyle, color: "var(--foreground)" }}
        >
          {symbol} {fmt(net, 0)}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)" }}>
          {interpolate(popo.monthly_dividend_gross, {
            amount: `${symbol} ${fmt(gross, 0)}`,
          })}
          {" · "}
          {interpolate(popo.monthly_dividend_cash_count, {
            count: String(cashCount),
          })}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {popo.monthly_dividend_hint}
          {stockCount > 0
            ? ` · ${interpolate(popo.monthly_dividend_stock_count, {
                count: String(stockCount),
              })}`
            : ""}
        </div>
      </div>
    );
  }

  return (
    <div style={gridStyle} className={gridClass}>
      {todayPnlNode}
      {dividendNode}
    </div>
  );
}
