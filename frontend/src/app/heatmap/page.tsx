"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { type HeatmapSector } from "@/lib/api-client";
import { TabGroup } from "@/components/ui/tab-group";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState } from "@/components/ui/empty-state";
import { useHeatmap } from "@/hooks/use-market-data";

function changeColor(pct: number): string {
  if (pct > 3) return "bg-red-600/90";
  if (pct > 1.5) return "bg-red-500/80";
  if (pct > 0.5) return "bg-red-500/50";
  if (pct > 0) return "bg-red-500/25";
  if (pct === 0) return "bg-[var(--card-hover)]";
  if (pct > -0.5) return "bg-green-500/25";
  if (pct > -1.5) return "bg-green-500/50";
  if (pct > -3) return "bg-green-500/80";
  return "bg-green-600/90";
}

function SectorBlock({ sector, onClick }: { sector: HeatmapSector; onClick: (symbol: string) => void }) {
  const isUp = sector.avg_change_percent >= 0;

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] overflow-hidden animate-shimmer">
      {/* Sector header */}
      <div className={`px-2.5 py-1.5 ${changeColor(sector.avg_change_percent)}`}>
        <div className="flex items-center justify-between">
          <span className="text-white font-semibold text-xs truncate">{sector.industry}</span>
          <span className={`text-[10px] font-bold mono-nums ${isUp ? "text-white glow-red" : "text-white glow-green"}`}>
            {isUp ? "+" : ""}{sector.avg_change_percent.toFixed(2)}%
          </span>
        </div>
        <span className="text-white/60 text-[10px] mono-nums">{sector.stock_count} stocks</span>
      </div>

      {/* Top stocks */}
      <div className="bg-[var(--card-bg)] p-1 space-y-0">
        {sector.stocks.map((stock) => {
          const sUp = stock.change_percent >= 0;
          return (
            <button
              key={stock.symbol}
              onClick={() => onClick(stock.symbol)}
              className="w-full flex items-center justify-between px-2 py-1 rounded hover:bg-[var(--card-hover)] transition-colors duration-100 text-left"
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-white text-[10px] mono-nums font-semibold">
                  {stock.symbol.replace(".TW", "").replace(".TWO", "")}
                </span>
                <span className="text-[var(--text-muted)] text-[10px] truncate">{stock.name}</span>
              </div>
              <span className={`text-[10px] mono-nums font-semibold shrink-0 ${sUp ? "text-[var(--stock-up)] glow-red" : "text-[var(--stock-down)] glow-green"}`}>
                {sUp ? "+" : ""}{stock.change_percent.toFixed(2)}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function HeatmapPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [marketFilter, setMarketFilter] = useState("TW_TWSE");

  const hm = t.heatmap;
  const filter = marketFilter === "all" ? undefined : marketFilter;
  const { data, isLoading: loading } = useHeatmap(filter);

  const marketTabs = [
    { key: "TW_TWSE", label: t.market?.twse ?? "TWSE" },
    { key: "TW_TPEX", label: t.market?.tpex ?? "TPEX" },
    { key: "all", label: t.market?.allMarkets ?? "All" },
  ];

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-white tracking-tight">
            {hm?.title ?? "Market Heatmap"}
          </h1>
          <p className="text-[var(--text-muted)] text-xs mt-0.5">
            {hm?.subtitle ?? "Sector performance overview"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TabGroup tabs={marketTabs} active={marketFilter} onChange={setMarketFilter} size="sm" />
          {data?.date && (
            <span className="text-[10px] text-[var(--text-muted)] mono-nums">{data.date}</span>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-1.5 mb-3 flex-wrap">
        <span className="text-[10px] text-[var(--text-muted)]">{hm?.legend ?? "Change"}:</span>
        <div className="flex items-center gap-0.5">
          <div className="w-3 h-2 rounded-sm bg-green-600/90" />
          <span className="text-[10px] text-[var(--text-muted)] mono-nums">&lt;-3%</span>
        </div>
        <div className="flex items-center gap-0.5">
          <div className="w-3 h-2 rounded-sm bg-green-500/50" />
          <span className="text-[10px] text-[var(--text-muted)] mono-nums">-1.5%</span>
        </div>
        <div className="flex items-center gap-0.5">
          <div className="w-3 h-2 rounded-sm bg-[var(--card-hover)]" />
          <span className="text-[10px] text-[var(--text-muted)] mono-nums">0%</span>
        </div>
        <div className="flex items-center gap-0.5">
          <div className="w-3 h-2 rounded-sm bg-red-500/50" />
          <span className="text-[10px] text-[var(--text-muted)] mono-nums">+1.5%</span>
        </div>
        <div className="flex items-center gap-0.5">
          <div className="w-3 h-2 rounded-sm bg-red-600/90" />
          <span className="text-[10px] text-[var(--text-muted)] mono-nums">&gt;+3%</span>
        </div>
      </div>

      {loading ? (
        <LoadingSpinner text={hm?.loading ?? "Loading heatmap..."} size="sm" />
      ) : data && data.sectors.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
          {data.sectors.map((sector) => (
            <SectorBlock
              key={sector.industry}
              sector={sector}
              onClick={(sym) => router.push(`/stocks/${encodeURIComponent(sym)}`)}
            />
          ))}
        </div>
      ) : (
        <EmptyState message={hm?.noData ?? "No heatmap data available"} />
      )}
    </div>
  );
}
