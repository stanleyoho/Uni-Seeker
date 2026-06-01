"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { type HeatmapSector } from "@/lib/api-client";
import { LoadingSpinner } from "@/components/ui/loading";
import { useHeatmap } from "@/hooks/use-market-data";
import { GlassPanel } from "@/components/stratos/primitives";
import { QuoteRow } from "@/components/quote-row";
import { classifySentiment, type SentimentLevel } from "@/lib/sentiment";

import { AmbientBackground } from "@/components/stratos/ambient";

/**
 * Per-level cell paint (border + fill). Spelled out as literal Tailwind
 * class strings so the JIT sees every class — derived/concatenated
 * class names would be tree-shaken at build time.
 */
const HEATMAP_CELL_PAINT: Record<SentimentLevel, { border: string; fill: string }> = {
  "过热": { border: "border-t-red-500", fill: "bg-red-500/15" },
  "上涨": { border: "border-t-orange-500", fill: "bg-orange-500/15" },
  "平": { border: "border-t-gray-500", fill: "bg-gray-500/10" },
  "下跌": { border: "border-t-sky-500", fill: "bg-sky-500/15" },
  "深跌": { border: "border-t-purple-500", fill: "bg-purple-500/15" },
};

function SectorBlock({ sector, onClick }: { sector: HeatmapSector; onClick: (symbol: string) => void }) {
  const avgChange = parseFloat(sector.avg_change_percent);
  // Today's intensity ramp was a green/red split (~9 buckets); replace
  // with the shared 5-level taxonomy so heatmap cells, scanner rows,
  // and low-base ranking speak the same signal language. Emoji prefix
  // doubles as a color-blind cue.
  const sentiment = classifySentiment(avgChange);
  const paint = HEATMAP_CELL_PAINT[sentiment.level];
  const isUp = avgChange >= 0;
  const pctText = `${isUp ? "+" : ""}${avgChange.toFixed(2)}%`;

  return (
    <GlassPanel
      noPadding
      className={`flex flex-col h-full border-t-4 ${paint.border}`}
    >
      <div className={`p-3 ${paint.fill} bg-gradient-to-b from-white/5 to-transparent`}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-[var(--foreground)] truncate pr-4">
            <span aria-hidden="true" className="mr-1">{sentiment.emoji}</span>
            {sector.industry}
          </h3>
          <span className={`text-sm font-bold tabular-nums ${sentiment.colorClass}`}>
            {sentiment.arrow} {pctText}
          </span>
        </div>
        <p className="text-[10px] text-[var(--text-muted)] font-bold uppercase tracking-widest">{sector.stock_count} STOCKS</p>
      </div>

      <div className="flex-1 p-2 space-y-1 bg-[var(--bg-secondary)]/30">
        {/*
          Heatmap detail rows used to show only the code + %. The user
          asked for the full quote set everywhere. HeatmapStock ships
          symbol/name/close/change_percent but no absolute change —
          QuoteRow derives it from price × pct internally so the line
          stays consistent with Market Movers.
        */}
        {sector.stocks.slice(0, 5).map((stock) => (
          <QuoteRow
            key={stock.symbol}
            variant="compact"
            symbol={stock.symbol}
            name={stock.name}
            price={stock.close}
            changePercent={stock.change_percent}
            onClick={() => onClick(stock.symbol)}
          />
        ))}
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
