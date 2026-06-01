"use client";

/**
 * RankingsPanel — 3-column ranks panel for the home dashboard.
 *
 * Columns: 漲幅排行 / 跌幅排行 / 成交量排行 (top 5 each).
 *
 * Data source: the existing `/api/v1/market/movers` endpoint already
 * returns all three buckets in one call — we make a single fetch and
 * fan it out into the three columns. This keeps the new widget free
 * of extra network round-trips.
 *
 * Layout budget: ~220px (8px header + 5 × ~36px rows = 188px + chrome).
 * Each column wraps in a GlassPanel so it harmonises with the rest of
 * the STRATOS dashboard. Rows are QuoteRow `default` variant which
 * already exposes symbol + name + price + abs + pct + clickable link.
 */

import React, { useMemo } from "react";
import { useMarketMovers } from "@/hooks/use-market-data";
import { GlassPanel } from "@/components/stratos/primitives";
import { QuoteRow } from "@/components/quote-row";
import type { MarketMover } from "@/lib/api-client";

const COLUMN_COUNT = 5;

interface ColumnSpec {
  key: "gainers" | "losers" | "active";
  emoji: string;
  title: string;
  english: string;
  accentVar: string;
}

const COLUMNS: ColumnSpec[] = [
  {
    key: "gainers",
    emoji: "🔴", // 紅 — 漲
    title: "漲幅排行",
    english: "Top Gainers",
    accentVar: "var(--stock-up)",
  },
  {
    key: "losers",
    emoji: "🟢", // 綠 — 跌
    title: "跌幅排行",
    english: "Top Losers",
    accentVar: "var(--stock-down)",
  },
  {
    key: "active",
    emoji: "📊",
    title: "成交量排行",
    english: "Most Active",
    accentVar: "var(--accent-cyan)",
  },
];

function RankSkeletonRow() {
  return (
    <div
      style={{
        height: 36,
        borderBottom: "1px solid rgba(255,255,255,0.04)",
        background: "rgba(255,255,255,0.02)",
      }}
    />
  );
}

function RankColumn({
  spec,
  movers,
  isLoading,
}: {
  spec: ColumnSpec;
  movers: MarketMover[];
  isLoading: boolean;
}) {
  // Clip to top-5. Backend already orders by the right direction, so we
  // just take the head — no resort needed.
  const top = movers.slice(0, COLUMN_COUNT);

  return (
    <GlassPanel className="flex flex-col min-h-0" noPadding style={{ padding: 12 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 6,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 3,
            height: 12,
            background: spec.accentVar,
            borderRadius: 1,
          }}
        />
        <span style={{ fontSize: 14, lineHeight: 1 }} aria-hidden="true">
          {spec.emoji}
        </span>
        <span
          className="text-[11px] font-bold uppercase tracking-[0.14em]"
          style={{ color: spec.accentVar }}
        >
          {spec.title}
        </span>
        <span
          className="text-[10px] font-semibold uppercase tracking-[0.04em]"
          style={{ color: "var(--text-muted)" }}
        >
          {spec.english}
        </span>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {isLoading
          ? Array.from({ length: COLUMN_COUNT }).map((_, i) => (
              <RankSkeletonRow key={i} />
            ))
          : top.length === 0
            ? (
              <div
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  color: "var(--text-muted)",
                }}
              >
                無資料
              </div>
            )
            : top.map((m, i) => (
                <QuoteRow
                  key={`${spec.key}-${m.symbol}`}
                  rank={i + 1}
                  symbol={m.symbol}
                  name={m.name}
                  price={m.close}
                  change={m.change}
                  changePercent={m.change_percent}
                  market={m.market}
                  href={`/stocks/${encodeURIComponent(m.symbol)}`}
                />
              ))}
      </div>
    </GlassPanel>
  );
}

export function RankingsPanel() {
  const { data, isLoading } = useMarketMovers();

  const byKey = useMemo(() => {
    return {
      gainers: data?.gainers ?? [],
      losers: data?.losers ?? [],
      active: data?.most_active ?? [],
    };
  }, [data]);

  return (
    <section style={{ flexShrink: 0 }}>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {COLUMNS.map((col) => (
          <RankColumn
            key={col.key}
            spec={col}
            movers={byKey[col.key]}
            isLoading={isLoading}
          />
        ))}
      </div>
    </section>
  );
}
