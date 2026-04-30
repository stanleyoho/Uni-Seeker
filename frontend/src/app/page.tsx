"use client";

import { useState } from "react";
import Link from "next/link";
import {
  type MarketIndex,
  type MarketMover,
} from "@/lib/api-client";
import { useI18n } from "@/i18n/context";
import { TabGroup } from "@/components/ui/tab-group";
import { LoadingSpinner } from "@/components/ui/loading";
import { useMarketIndices, useMarketMovers } from "@/hooks/use-market-data";

// ── Status Bar ─────────────────────────────────────────────────

function StatusBar() {
  const now = new Date();
  const dateStr = now.toLocaleDateString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });
  const timeStr = now.toLocaleTimeString("zh-TW", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-[var(--bg-secondary)] border-b border-[var(--border-subtle)] rounded-t-lg">
      <div className="flex items-center gap-2">
        <span className="status-dot" />
        <span className="text-[var(--foreground)] text-xs font-semibold tracking-wide">
          Uni-Seeker 戰情室
        </span>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)] mono-nums">
        <span>{dateStr} {timeStr}</span>
        <span className="text-[var(--score-excellent)] font-medium">MARKET OPEN</span>
      </div>
    </div>
  );
}

// ── Market Index Card ──────────────────────────────────────────

function IndexCard({ idx }: { idx: MarketIndex }) {
  const isUp = idx.change >= 0;

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-md px-2.5 py-2 hover:bg-[var(--card-hover)] transition-colors duration-150">
      <div className="text-[10px] text-[var(--text-muted)] font-medium uppercase tracking-wider truncate mb-0.5">
        {idx.name}
      </div>
      <div className="flex items-end justify-between gap-2">
        <div className="text-sm font-bold text-[var(--foreground)] mono-nums leading-tight">
          {idx.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </div>
        <div className="text-right">
          <div
            className={`text-xs font-semibold mono-nums leading-tight ${
              isUp
                ? "text-[var(--stock-up)] glow-red"
                : "text-[var(--stock-down)] glow-green"
            }`}
          >
            {isUp ? "+" : ""}
            {idx.change_percent.toFixed(2)}%
          </div>
          <div
            className={`text-[10px] mono-nums leading-tight ${
              isUp ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"
            }`}
          >
            {isUp ? "+" : ""}
            {idx.change.toFixed(2)}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Index Ticker Grid ──────────────────────────────────────────

function IndexTickerGrid({ indices }: { indices: MarketIndex[] }) {
  if (indices.length === 0) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-2">
      {indices.map((idx) => (
        <IndexCard key={idx.symbol} idx={idx} />
      ))}
    </div>
  );
}

// ── Mover Row ───────────────────────────────────────────────────

function MoverRow({ mover, rank }: { mover: MarketMover; rank: number }) {
  const isUp = mover.change >= 0;

  return (
    <Link
      href={`/stocks/${encodeURIComponent(mover.symbol)}`}
      className="flex items-center gap-2 px-2.5 py-1.5 hover:bg-[var(--card-hover)] rounded-md transition-colors duration-100 group"
    >
      <span className="text-[var(--text-muted)] text-[10px] mono-nums w-4 shrink-0">
        {rank}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[var(--foreground)] font-semibold text-xs group-hover:text-[var(--accent-blue)] transition-colors">
            {mover.symbol.replace(".TW", "").replace(".TWO", "")}
          </span>
          <span className="text-[var(--text-muted)] text-[10px] truncate">
            {mover.name}
          </span>
        </div>
      </div>
      <div className="text-right shrink-0 flex items-center gap-2">
        <span className="text-[var(--foreground)] text-xs mono-nums">
          {mover.close.toFixed(2)}
        </span>
        <span
          className={`text-[10px] font-semibold mono-nums min-w-[48px] text-right ${
            isUp
              ? "text-[var(--stock-up)] glow-red"
              : "text-[var(--stock-down)] glow-green"
          }`}
        >
          {isUp ? "+" : ""}
          {mover.change_percent.toFixed(2)}%
        </span>
      </div>
    </Link>
  );
}

// ── Movers Card ─────────────────────────────────────────────────

function MoversCard({
  title,
  movers,
}: {
  title: string;
  movers: MarketMover[];
}) {
  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--border-subtle)]">
        <h3 className="text-[var(--text-secondary)] font-medium text-xs uppercase tracking-wider">
          {title}
        </h3>
      </div>
      <div className="p-1 space-y-0">
        {movers.length === 0 ? (
          <div className="px-2.5 py-3 text-center text-[var(--text-muted)] text-[10px]">
            暫無資料
          </div>
        ) : (
          movers
            .slice(0, 10)
            .map((m, i) => <MoverRow key={m.symbol} mover={m} rank={i + 1} />)
        )}
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────

export default function HomePage() {
  const { t } = useI18n();
  const [marketFilter, setMarketFilter] = useState<string>("all");

  const m = t.market;

  const { data: indices = [], isLoading: indicesLoading } = useMarketIndices();
  const filter = marketFilter === "all" ? undefined : marketFilter;
  const { data: movers, isLoading: moversLoading } = useMarketMovers(filter);
  const marketLoading = indicesLoading || moversLoading;

  const marketTabs = [
    { key: "all", label: m.allMarkets },
    { key: "TW_TWSE", label: m.twse },
    { key: "TW_TPEX", label: m.tpex },
    { key: "US_NYSE", label: m.us },
  ];

  return (
    <div className="min-h-screen flex flex-col max-w-[1440px] mx-auto w-full px-2 md:px-3 py-2 animate-fade-in">
      {/* 1. Status Bar */}
      <StatusBar />

      {/* 2. Index Ticker Grid */}
      <div className="mt-2">
        {indicesLoading ? (
          <LoadingSpinner size="sm" />
        ) : (
          <IndexTickerGrid indices={indices} />
        )}
      </div>

      {/* 3. Section Divider + Tabs Inline */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mt-3 mb-2">
        <div className="flex items-center gap-2">
          <div className="w-0.5 h-4 bg-[var(--accent-blue)] rounded-full" />
          <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
            {m.overview}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <TabGroup
            tabs={marketTabs}
            active={marketFilter}
            onChange={setMarketFilter}
            size="sm"
          />
          {movers?.date && (
            <span className="text-[10px] text-[var(--text-muted)] mono-nums">
              {m.asOf} {movers.date}
            </span>
          )}
        </div>
      </div>

      {/* 4. Three-Column Mover Grid */}
      {moversLoading ? (
        <LoadingSpinner size="sm" />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <MoversCard title={m.gainers} movers={movers?.gainers ?? []} />
          <MoversCard title={m.losers} movers={movers?.losers ?? []} />
          <MoversCard title={m.mostActive} movers={movers?.most_active ?? []} />
        </div>
      )}

      {/* 5. Quick Tools */}
      <div className="border-t border-[var(--border-subtle)] pt-2 mt-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="text-[var(--text-muted)] uppercase tracking-wider text-[10px] mr-1">
            Quick
          </span>
          <Link
            href="/screener"
            className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors"
          >
            {t.nav.screener}
          </Link>
          <Link
            href="/backtest"
            className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors"
          >
            {t.nav.backtest}
          </Link>
          <Link
            href="/low-base"
            className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors"
          >
            {t.nav.lowBase}
          </Link>
          <Link
            href="/heatmap"
            className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors"
          >
            {t.nav.heatmap}
          </Link>
          <Link
            href="/compare"
            className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors"
          >
            {t.nav.compare}
          </Link>
          <Link
            href="/watchlist"
            className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors"
          >
            {t.nav.watchlist}
          </Link>
        </div>
      </div>
    </div>
  );
}
