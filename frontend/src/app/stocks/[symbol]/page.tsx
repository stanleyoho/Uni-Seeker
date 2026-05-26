"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { StockChart } from "@/components/charts/stock-chart";
import { IndicatorPanel } from "./components/indicator-panel";
import { ValuationPanel } from "./components/valuation-panel";
import { type MarginData, type RevenueAnalysis } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

type I18nMessages = ReturnType<typeof useI18n>["t"];
import { StatCard } from "@/components/ui/stat-card";
import { LoadingSpinner } from "@/components/ui/loading";
import { ScoreBar } from "@/components/ui/score-bar";
import { GlassPanel, KpiCard, ClippedButton } from "@/components/stratos/primitives";
import { useWatchlist } from "@/hooks/use-watchlist";
import { usePrices, useCompanyInfo, useMarginData, useRevenue, useValuation } from "@/hooks/use-market-data";
import { AmbientBackground } from "@/components/stratos/ambient";

const TIMEFRAMES = [
  { key: "30", label: "1M" },
  { key: "90", label: "3M" },
  { key: "120", label: "6M" },
  { key: "250", label: "1Y" },
  { key: "500", label: "2Y" },
];

function MarginPanel({ margin, t }: { margin: MarginData; t: I18nMessages }) {
  const s = t.stock;
  return (
    <GlassPanel title={s.margin}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <StatCard label={s.marginBalance} value={margin.margin_balance.toLocaleString()} size="sm" />
        <StatCard label={s.shortBalance} value={margin.short_balance.toLocaleString()} size="sm" />
        <StatCard label={s.marginShortRatio} value={`${margin.margin_short_ratio}%`} size="sm" />
        <StatCard label={s.offset} value={margin.offset.toLocaleString()} size="sm" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Margin */}
        <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border-subtle)]">
          <h4 className="text-[var(--text-secondary)] text-[10px] uppercase tracking-wider font-medium mb-2">
            {s.marginBalance} ({s.marginUsage})
          </h4>
          <ScoreBar label={s.marginUsage} value={margin.margin_usage_pct} size="md" />
          <div className="mt-2.5 grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <span className="text-[var(--text-muted)]">{s.marginBuy}</span>
              <p className="text-[var(--foreground)] mt-0.5" style={{ fontVariantNumeric: "tabular-nums" }}>{margin.margin_buy.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.marginSell}</span>
              <p className="text-[var(--foreground)] mt-0.5" style={{ fontVariantNumeric: "tabular-nums" }}>{margin.margin_sell.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.marginLimit}</span>
              <p className="text-[var(--foreground)] mt-0.5" style={{ fontVariantNumeric: "tabular-nums" }}>{margin.margin_limit.toLocaleString()}</p>
            </div>
          </div>
        </div>

        {/* Short */}
        <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border-subtle)]">
          <h4 className="text-[var(--text-secondary)] text-[10px] uppercase tracking-wider font-medium mb-2">
            {s.shortBalance} ({s.shortUsage})
          </h4>
          <ScoreBar label={s.shortUsage} value={margin.short_usage_pct} size="md" />
          <div className="mt-2.5 grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <span className="text-[var(--text-muted)]">{s.shortBuy}</span>
              <p className="text-[var(--foreground)] mt-0.5" style={{ fontVariantNumeric: "tabular-nums" }}>{margin.short_buy.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.shortSell}</span>
              <p className="text-[var(--foreground)] mt-0.5" style={{ fontVariantNumeric: "tabular-nums" }}>{margin.short_sell.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.shortLimit}</span>
              <p className="text-[var(--foreground)] mt-0.5" style={{ fontVariantNumeric: "tabular-nums" }}>{margin.short_limit.toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}

function RevenuePanel({ revenue, t }: { revenue: RevenueAnalysis; t: I18nMessages }) {
  const formatRevenue = (v: number | string) => {
    const val = typeof v === "string" ? parseFloat(v) : v;
    if (isNaN(val)) return "-";
    if (val >= 1e9) return `${(val / 1e9).toFixed(1)}B`;
    if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
    if (val >= 1e3) return `${(val / 1e3).toFixed(1)}K`;
    return val.toFixed(0);
  };

  const formatPct = (v: number | string | null) => {
    if (v == null) return "-";
    const val = typeof v === "string" ? parseFloat(v) : v;
    if (isNaN(val)) return "-";
    return `${(val * 100).toFixed(1)}%`;
  };

  const yoyGrowth = revenue.yoy_growth != null ? parseFloat(revenue.yoy_growth) : null;
  const qoqGrowth = revenue.qoq_growth != null ? parseFloat(revenue.qoq_growth) : null;

  return (
    <GlassPanel title={t.stock?.revenue ?? "Revenue"}>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard
          label={t.stock?.latestRevenue ?? "Latest Revenue"}
          value={formatRevenue(revenue.latest_revenue)}
          delta={`${revenue.trend === "up" ? "+" : ""}${revenue.consecutive_growth_quarters}Q`}
          direction={revenue.trend === "up" ? "up" : "down"}
        />
        <KpiCard
          label="YoY Growth"
          value={formatPct(revenue.yoy_growth)}
          delta={`${yoyGrowth != null && yoyGrowth > 0 ? "+" : ""}`}
          direction={yoyGrowth != null && yoyGrowth > 0 ? "up" : "down"}
        />
        <KpiCard
          label="QoQ Growth"
          value={formatPct(revenue.qoq_growth)}
          delta=""
          direction={qoqGrowth != null && qoqGrowth > 0 ? "up" : "down"}
        />
        <KpiCard
          label="Stability Score"
          value={revenue.consecutive_growth_quarters >= 2 ? "High" : "Mid"}
          delta="Trend"
          direction="flat"
        />
      </div>

      {/* Revenue History Chart */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-[11px] uppercase tracking-wider text-[var(--text-secondary)] font-bold">
            Revenue History (Last 8 Periods)
          </h4>
          <div className="flex gap-2">
            {revenue.is_revenue_high && (
              <span className="px-2 py-0.5 rounded bg-[var(--stock-up-bg)] text-[var(--stock-up)] text-[10px] font-bold border border-[var(--stock-up)]/20">
                {t.stock?.revenueHigh ?? "REVENUE HIGH"}
              </span>
            )}
          </div>
        </div>
        
        <div className="h-[160px] w-full flex items-end gap-2 px-2 pb-2">
          {revenue.records.slice(-8).map((rec) => {
            const records = revenue.records.slice(-8);
            const maxRev = Math.max(...records.map((r) => parseFloat(r.revenue)));
            const currentRev = parseFloat(rec.revenue);
            const height = maxRev > 0 ? (currentRev / maxRev) * 100 : 0;
            return (
              <div key={rec.period} className="flex-1 flex flex-col items-center gap-2 group">
                <div className="relative w-full flex items-end justify-center">
                  <div
                    className="w-full max-w-[40px] bg-[var(--accent-primary)] opacity-40 group-hover:opacity-100 transition-all duration-300"
                    style={{ 
                      height: `${height}%`, 
                      minHeight: "4px",
                      clipPath: "polygon(0 0, 100% 0, 100% 100%, 0 100%)",
                      backgroundImage: "linear-gradient(to top, var(--accent-primary), transparent)"
                    }}
                  />
                  <div className="absolute -top-6 opacity-0 group-hover:opacity-100 transition-opacity bg-[var(--bg-secondary)] border border-[var(--border-subtle)] px-2 py-1 rounded text-[10px] tabular-nums whitespace-nowrap z-10">
                    {formatRevenue(rec.revenue)}
                  </div>
                </div>
                <span className="text-[var(--text-muted)] text-[10px] tabular-nums">
                  {rec.period.slice(-5)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </GlassPanel>
  );
}

export default function StockDetailPage() {
  const { t } = useI18n();
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [timeframe, setTimeframe] = useState("120");
  const [activeTab, setActiveTab] = useState("chart");
  const watchlist = useWatchlist();

  const { data: priceData, isLoading: loading } = usePrices(symbol, Number(timeframe));
  const { data: companyInfo } = useCompanyInfo(symbol);
  const isTWSymbol = symbol.includes(".TW");
  const { data: marginData, isLoading: marginLoading } = useMarginData(symbol, activeTab === "margin" && isTWSymbol);
  const { data: revenueData, isLoading: revenueLoading } = useRevenue(symbol, activeTab === "revenue");
  const { data: valuationData, isLoading: valuationLoading } = useValuation(symbol, activeTab === "valuation");

  const prices = priceData?.data ?? [];

  if (loading && prices.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center h-screen bg-[var(--background)]">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  const latestPrice = prices.length > 0 ? prices[0] : null;
  const isUp = latestPrice ? parseFloat(latestPrice.change) >= 0 : true;

  const tabs = [
    { key: "chart", label: "Overview" },
    { key: "indicators", label: "Analysis" },
    { key: "valuation", label: "Valuation" },
    { key: "revenue", label: "Financials" },
    ...(isTWSymbol ? [{ key: "margin", label: "Flows" }] : []),
  ];

  return (
    <div className="flex-1 bg-[var(--background)] relative min-h-0 overflow-y-auto">
      <AmbientBackground />
      
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6">
        
        {/* -- 1. Header Section -- */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-8">
            <GlassPanel className="h-full flex flex-col justify-center">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-4">
                  <div className="h-12 w-12 bg-[var(--accent-primary)] flex items-center justify-center text-white font-bold text-xl clip-path-polygon">
                    {symbol[0]}
                  </div>
                  <div>
                    <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)]">{symbol}</h1>
                    <p className="text-[var(--text-secondary)] text-sm font-medium">{companyInfo?.name || "Stock Analysis"}</p>
                  </div>
                </div>
                <ClippedButton 
                  variant={watchlist.has(symbol) ? "white-solid" : "red-solid"} 
                  size="sm"
                  onClick={() => watchlist.toggle(symbol, companyInfo?.name ?? symbol, latestPrice?.market ?? "")}
                >
                  {watchlist.has(symbol) ? "UNFOLLOW" : "FOLLOW"}
                </ClippedButton>
              </div>

              <div className="flex flex-wrap gap-2">
                {companyInfo?.industry && (
                  <span className="px-2 py-0.5 text-[10px] font-bold bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] uppercase tracking-widest">
                    {companyInfo.industry}
                  </span>
                )}
                <span className="px-2 py-0.5 text-[10px] font-bold bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--text-secondary)] uppercase tracking-widest">
                  {latestPrice?.market || "MARKET"}
                </span>
              </div>
            </GlassPanel>
          </div>

          <div className="lg:col-span-4">
            {latestPrice && (
              <KpiCard
                label="Current Price"
                value={parseFloat(latestPrice.close).toLocaleString()}
                delta={`${isUp ? "+" : ""}${parseFloat(latestPrice.change_percent).toFixed(2)}%`}
                direction={isUp ? "up" : "down"}
              />
            )}
          </div>
        </div>

        {/* -- 2. Navigation Tabs -- */}
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-px">
          <div className="flex gap-8">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`pb-3 text-sm font-bold tracking-tight transition-all relative ${
                  activeTab === tab.key ? "text-[var(--foreground)]" : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                }`}
              >
                {tab.label.toUpperCase()}
                {activeTab === tab.key && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--accent-primary)]" />
                )}
              </button>
            ))}
          </div>
          <Link 
            href={`/stocks/${encodeURIComponent(symbol)}/financials`}
            className="text-xs font-bold text-[var(--accent-cyan)] hover:brightness-110 transition-all mb-3"
          >
            VIEW FULL STATEMENTS →
          </Link>
        </div>

        {/* -- 3. Content Area -- */}
        <div className="min-h-[600px]">
          {activeTab === "chart" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-9">
                <GlassPanel title="Market Performance" noPadding>
                  <div className="p-4 flex flex-col h-full">
                    <div className="flex justify-end mb-4">
                      <div className="flex bg-[var(--bg-secondary)] p-1 rounded border border-[var(--border-subtle)]">
                        {TIMEFRAMES.map((tf) => (
                          <button
                            key={tf.key}
                            onClick={() => setTimeframe(tf.key)}
                            className={`px-3 py-1 text-[10px] font-bold transition-all ${
                              timeframe === tf.key 
                              ? "bg-[var(--accent-primary)] text-white" 
                              : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
                            }`}
                          >
                            {tf.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    <StockChart prices={prices} height={500} />
                  </div>
                </GlassPanel>
              </div>

              <div className="lg:col-span-3 space-y-4">
                <GlassPanel title="Daily Stats">
                  <div className="space-y-4">
                    <div className="flex justify-between border-b border-[var(--border-subtle)] pb-2">
                      <span className="text-[11px] text-[var(--text-muted)] font-medium">OPEN</span>
                      <span className="text-sm font-bold tabular-nums">{parseFloat(latestPrice?.open || "0").toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between border-b border-[var(--border-subtle)] pb-2">
                      <span className="text-[11px] text-[var(--text-muted)] font-medium">HIGH</span>
                      <span className="text-sm font-bold tabular-nums">{parseFloat(latestPrice?.high || "0").toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between border-b border-[var(--border-subtle)] pb-2">
                      <span className="text-[11px] text-[var(--text-muted)] font-medium">LOW</span>
                      <span className="text-sm font-bold tabular-nums">{parseFloat(latestPrice?.low || "0").toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between border-b border-[var(--border-subtle)] pb-2">
                      <span className="text-[11px] text-[var(--text-muted)] font-medium">VOLUME</span>
                      <span className="text-sm font-bold tabular-nums">{latestPrice?.volume.toLocaleString()}</span>
                    </div>
                  </div>
                </GlassPanel>

                <GlassPanel title="Analysis Context">
                  <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed">
                    Based on recent performance, {symbol} is currently {isUp ? "showing bullish momentum" : "facing downward pressure"}. 
                    Switch to Analysis tab for technical indicators.
                  </p>
                </GlassPanel>
              </div>
            </div>
          )}

          {activeTab === "indicators" && (
            <div className="animate-fade-up">
              <IndicatorPanel prices={prices} t={t} />
            </div>
          )}

          {activeTab === "valuation" && (
            <div className="animate-fade-up">
              {valuationLoading ? (
                <div className="h-64 flex items-center justify-center"><LoadingSpinner /></div>
              ) : valuationData ? (
                <ValuationPanel valuation={valuationData} currentPrice={latestPrice ? parseFloat(latestPrice.close) : 0} />
              ) : (
                <GlassPanel><div className="py-20 text-center text-[var(--text-muted)]">No valuation data available</div></GlassPanel>
              )}
            </div>
          )}

          {activeTab === "revenue" && (
            <div className="animate-fade-up">
              {revenueLoading ? (
                <div className="h-64 flex items-center justify-center"><LoadingSpinner /></div>
              ) : revenueData ? (
                <RevenuePanel revenue={revenueData} t={t} />
              ) : (
                <GlassPanel><div className="py-20 text-center text-[var(--text-muted)]">No revenue data available</div></GlassPanel>
              )}
            </div>
          )}

          {activeTab === "margin" && isTWSymbol && (
            <div className="animate-fade-up">
              {marginLoading ? (
                <div className="h-64 flex items-center justify-center"><LoadingSpinner /></div>
              ) : marginData ? (
                <MarginPanel margin={marginData} t={t} />
              ) : (
                <GlassPanel><div className="py-20 text-center text-[var(--text-muted)]">No margin data available</div></GlassPanel>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
