"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { type HeatmapSector } from "@/lib/api-client";
import { LoadingSpinner } from "@/components/ui/loading";
import { useHeatmap } from "@/hooks/use-market-data";
import { GlassPanel } from "@/components/stratos/primitives";

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

import { AmbientBackground } from "@/components/stratos/ambient";

function SectorBlock({ sector, onClick }: { sector: HeatmapSector; onClick: (symbol: string) => void }) {
  const avgChange = parseFloat(sector.avg_change_percent);
  const isUp = avgChange >= 0;
  const pctText = `${isUp ? "+" : ""}${avgChange.toFixed(2)}%`;

  return (
    <GlassPanel 
      noPadding 
      className="flex flex-col h-full border-t-2" 
      style={{ borderTopColor: changeColor(avgChange) }}
    >
      <div className="p-3 bg-gradient-to-b from-white/5 to-transparent">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-[var(--foreground)] truncate pr-4">{sector.industry}</h3>
          <span className="text-sm font-bold tabular-nums" style={{ color: isUp ? "var(--stock-up)" : "var(--stock-down)" }}>
            {pctText}
          </span>
        </div>
        <p className="text-[10px] text-[var(--text-muted)] font-bold uppercase tracking-widest">{sector.stock_count} STOCKS</p>
      </div>

      <div className="flex-1 p-2 space-y-1 bg-[var(--bg-secondary)]/30">
        {sector.stocks.slice(0, 5).map((stock) => {
          const sChange = parseFloat(stock.change_percent);
          const sUp = sChange >= 0;
          return (
            <button
              key={stock.symbol}
              onClick={() => onClick(stock.symbol)}
              className="w-full flex items-center justify-between px-2 py-1 hover:bg-[var(--card-hover)] transition-colors text-left"
            >
              <span className="text-[11px] font-bold text-[var(--foreground)] tabular-nums">{stock.symbol.split('.')[0]}</span>
              <span className={`text-[11px] font-bold tabular-nums ${sUp ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}>
                {sUp ? "+" : ""}{sChange.toFixed(2)}%
              </span>
            </button>
          );
        })}
      </div>
    </GlassPanel>
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
    { key: "TW_TWSE", label: "TAIWAN SE (TWSE)" },
    { key: "TW_TPEX", label: "TAIPEI EXCHANGE (TPEX)" },
    { key: "all", label: "GLOBAL VIEW" },
  ];

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 border-b border-[var(--border-subtle)] pb-4 gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              {hm?.title ?? "Market Heatmap"}
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              {hm?.subtitle ?? "Sector Performance Terminal"}
            </p>
          </div>
          <div className="flex bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-1">
            {marketTabs.map(tab => (
              <button
                key={tab.key}
                onClick={() => setMarketFilter(tab.key)}
                className={`px-4 py-1 text-[10px] font-bold transition-all ${
                  marketFilter === tab.key ? "bg-[var(--accent-primary)] text-white" : "text-[var(--text-secondary)] hover:text-[var(--foreground)]"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="py-20 flex justify-center"><LoadingSpinner /></div>
        ) : data && data.sectors.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {data.sectors.map((sector) => (
              <SectorBlock
                key={sector.industry}
                sector={sector}
                onClick={(sym) => router.push(`/stocks/${encodeURIComponent(sym)}`)}
              />
            ))}
          </div>
        ) : (
          <GlassPanel className="py-24 text-center">
            <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-[0.2em]">NO DATA AVAILABLE</p>
          </GlassPanel>
        )}
      </main>
    </div>
  );
}
