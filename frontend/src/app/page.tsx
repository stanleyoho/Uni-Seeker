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

// ── Market Index Ticker ─────────────────────────────────────────

function IndexTicker({ indices }: { indices: MarketIndex[] }) {
  if (indices.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2">
      {indices.map((idx) => {
        const isUp = idx.change >= 0;
        return (
          <div
            key={idx.symbol}
            className="flex items-center gap-3 bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg px-3 py-2 min-w-[180px] hover:bg-[var(--card-hover)] transition-colors duration-150"
          >
            <div className="flex-1 min-w-0">
              <div className="text-[10px] text-[var(--text-muted)] font-medium uppercase tracking-wider truncate">{idx.name}</div>
              <div className="text-base font-bold text-white mono-nums">
                {idx.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className={`text-xs font-semibold mono-nums ${isUp ? "text-[var(--stock-up)] glow-red" : "text-[var(--stock-down)] glow-green"}`}>
                {isUp ? "+" : ""}{idx.change_percent.toFixed(2)}%
              </div>
              <div className={`text-[10px] mono-nums ${isUp ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}>
                {isUp ? "+" : ""}{idx.change.toFixed(2)}
              </div>
            </div>
          </div>
        );
      })}
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
      <span className="text-[var(--text-muted)] text-[10px] mono-nums w-4 shrink-0">{rank}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-white font-semibold text-xs group-hover:text-[var(--accent-blue)] transition-colors">
            {mover.symbol.replace(".TW", "").replace(".TWO", "")}
          </span>
          <span className="text-[var(--text-muted)] text-[10px] truncate">{mover.name}</span>
        </div>
      </div>
      <div className="text-right shrink-0 flex items-center gap-2">
        <span className="text-white text-xs mono-nums">{mover.close.toFixed(2)}</span>
        <span className={`text-[10px] font-semibold mono-nums min-w-[48px] text-right ${isUp ? "text-[var(--stock-up)] glow-red" : "text-[var(--stock-down)] glow-green"}`}>
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
  if (movers.length === 0) return null;

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--border-subtle)]">
        <h3 className="text-[var(--text-secondary)] font-medium text-xs uppercase tracking-wider">{title}</h3>
      </div>
      <div className="p-1 space-y-0">
        {movers.slice(0, 10).map((m, i) => (
          <MoverRow key={m.symbol} mover={m} rank={i + 1} />
        ))}
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────

export default function HomePage() {
  const { t } = useI18n();

  // Market data via React Query
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
    <div className="min-h-screen flex flex-col p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      {/* Compact Hero + Search hint */}
      <div className="flex flex-col items-center py-4 md:py-6">
        <h1 className="text-2xl md:text-3xl font-bold mb-1 gradient-text tracking-tight">
          {t.app.title}
        </h1>
        <p className="text-[var(--text-muted)] mb-4 text-sm">{t.app.subtitle}</p>

        <p className="text-[var(--text-muted)] text-xs flex items-center gap-1.5">
          {t.search.hint}
          <kbd className="inline-flex items-center justify-center text-[10px] text-[var(--text-muted)] border border-[var(--border-color)] rounded px-1.5 py-0.5 font-mono leading-none">F</kbd>
        </p>
      </div>

      {/* Market Index Ticker */}
      {marketLoading ? (
        <LoadingSpinner size="sm" />
      ) : (
        <>
          {indices.length > 0 && (
            <div className="mb-4">
              <IndexTicker indices={indices} />
            </div>
          )}

          {/* Market Movers */}
          {movers && (movers.gainers.length > 0 || movers.losers.length > 0 || movers.most_active.length > 0) && (
            <div className="mb-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
                <h2 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider">{m.overview}</h2>
                <div className="flex items-center gap-2">
                  <TabGroup tabs={marketTabs} active={marketFilter} onChange={setMarketFilter} size="sm" />
                  {movers.date && (
                    <span className="text-[10px] text-[var(--text-muted)] mono-nums">
                      {movers.date}
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <MoversCard title={m.gainers} movers={movers.gainers} />
                <MoversCard title={m.losers} movers={movers.losers} />
                <MoversCard title={m.mostActive} movers={movers.most_active} />
              </div>
            </div>
          )}
        </>
      )}

      {/* Quick Access - simplified text links */}
      <div className="border-t border-[var(--border-subtle)] pt-3 mb-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="text-[var(--text-muted)] uppercase tracking-wider mr-1">Quick</span>
          <Link href="/screener" className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors">{t.nav.screener}</Link>
          <Link href="/backtest" className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors">{t.nav.backtest}</Link>
          <Link href="/low-base" className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors">{t.nav.lowBase}</Link>
          <Link href="/heatmap" className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors">{t.nav.heatmap}</Link>
          <Link href="/compare" className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors">{t.nav.compare}</Link>
          <Link href="/watchlist" className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition-colors">{t.nav.watchlist}</Link>
        </div>
      </div>

      {/* Footer stats */}
      <div className="flex items-center justify-center gap-4 text-[var(--text-muted)] text-[10px] py-2 border-t border-[var(--border-subtle)]">
        <div className="flex items-center gap-1.5">
          <span className="status-dot" />
          <span>TW + US Markets</span>
        </div>
        <span className="text-[var(--border-color)]">|</span>
        <span>15+ Indicators</span>
        <span className="text-[var(--border-color)]">|</span>
        <span>Real-time Analysis</span>
      </div>
    </div>
  );
}
