"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { StockChart } from "@/components/charts/stock-chart";
import { type MarginData, type RevenueAnalysis } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";
import { StatCard } from "@/components/ui/stat-card";
import { ChangeBadge, Badge } from "@/components/ui/badge";
import { TabGroup } from "@/components/ui/tab-group";
import { LoadingSpinner } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/empty-state";
import { ScoreBar } from "@/components/ui/score-bar";
import { useWatchlist } from "@/hooks/use-watchlist";
import { usePrices, useCompanyInfo, useMarginData, useRevenue } from "@/hooks/use-market-data";

const TIMEFRAMES = [
  { key: "30", label: "1M" },
  { key: "90", label: "3M" },
  { key: "120", label: "6M" },
  { key: "250", label: "1Y" },
  { key: "500", label: "2Y" },
];

function MarginPanel({ margin, t }: { margin: MarginData; t: Record<string, any> }) {
  const s = t.stock;
  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
      <h3 className="text-xs font-semibold mb-3 text-[var(--text-secondary)] uppercase tracking-wider">{s.margin}</h3>

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
              <p className="text-white mono-nums mt-0.5">{margin.margin_buy.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.marginSell}</span>
              <p className="text-white mono-nums mt-0.5">{margin.margin_sell.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.marginLimit}</span>
              <p className="text-white mono-nums mt-0.5">{margin.margin_limit.toLocaleString()}</p>
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
              <p className="text-white mono-nums mt-0.5">{margin.short_buy.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.shortSell}</span>
              <p className="text-white mono-nums mt-0.5">{margin.short_sell.toLocaleString()}</p>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">{s.shortLimit}</span>
              <p className="text-white mono-nums mt-0.5">{margin.short_limit.toLocaleString()}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function RevenuePanel({ revenue, t }: { revenue: RevenueAnalysis; t: Record<string, any> }) {
  const formatRevenue = (v: number) => {
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toFixed(0);
  };

  const formatPct = (v: number | null) => {
    if (v == null) return "-";
    return `${(v * 100).toFixed(1)}%`;
  };

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
      <h3 className="text-xs font-semibold mb-3 text-[var(--text-secondary)] uppercase tracking-wider">{t.stock?.revenue ?? "Revenue"}</h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <StatCard label={t.stock?.latestRevenue ?? "Latest Revenue"} value={formatRevenue(revenue.latest_revenue)} size="sm" />
        <StatCard
          label="QoQ"
          value={formatPct(revenue.qoq_growth)}
          change={revenue.qoq_growth != null ? revenue.qoq_growth * 100 : undefined}
          size="sm"
        />
        <StatCard
          label="YoY"
          value={formatPct(revenue.yoy_growth)}
          change={revenue.yoy_growth != null ? revenue.yoy_growth * 100 : undefined}
          size="sm"
        />
        <StatCard
          label={t.stock?.trend ?? "Trend"}
          value={`${revenue.trend} (${revenue.consecutive_growth_quarters}Q)`}
          size="sm"
        />
      </div>

      {/* Revenue badges */}
      <div className="flex gap-1.5 mb-3">
        {revenue.is_revenue_high && (
          <Badge variant="up">{t.stock?.revenueHigh ?? "Revenue High"}</Badge>
        )}
        {revenue.is_revenue_low && (
          <Badge variant="down">{t.stock?.revenueLow ?? "Revenue Low"}</Badge>
        )}
      </div>

      {/* Revenue bar chart (last 8 periods) */}
      {revenue.records.length > 0 && (
        <div className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border-subtle)]">
          <div className="flex items-end gap-1 h-28">
            {revenue.records.slice(-8).map((rec) => {
              const maxRev = Math.max(...revenue.records.slice(-8).map((r) => r.revenue));
              const height = maxRev > 0 ? (rec.revenue / maxRev) * 100 : 0;
              return (
                <div key={rec.period} className="flex-1 flex flex-col items-center gap-0.5">
                  <div
                    className="w-full bg-[var(--accent-blue)]/50 hover:bg-[var(--accent-blue)] rounded-t transition-all duration-200"
                    style={{ height: `${height}%`, minHeight: "2px" }}
                    title={`${rec.period}: ${formatRevenue(rec.revenue)}`}
                  />
                  <span className="text-[var(--text-muted)] text-[8px] mono-nums truncate w-full text-center">
                    {rec.period.slice(-5)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function StockDetailPage() {
  const { t } = useI18n();
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [timeframe, setTimeframe] = useState("120");
  const [activeTab, setActiveTab] = useState("chart");
  const watchlist = useWatchlist();

  const { data: priceData, isLoading: loading, error: priceError } = usePrices(symbol, Number(timeframe));
  const { data: companyInfo } = useCompanyInfo(symbol);
  const isTWSymbol = symbol.includes(".TW");
  const { data: marginData, isLoading: marginLoading } = useMarginData(symbol, activeTab === "margin" && isTWSymbol);
  const { data: revenueData, isLoading: revenueLoading } = useRevenue(symbol, activeTab === "revenue");

  const prices = priceData?.data ?? [];
  const error = priceError ? (priceError as Error).message : null;

  if (loading && prices.length === 0) {
    return <LoadingSpinner text={t.stock.loading} fullPage />;
  }

  if (error && prices.length === 0) {
    return (
      <div className="p-6 max-w-md mx-auto">
        <ErrorState message={error} />
      </div>
    );
  }

  const latestPrice = prices.length > 0 ? prices[0] : null;
  const change = latestPrice ? parseFloat(latestPrice.change) : 0;
  const changePct = latestPrice ? latestPrice.change_percent : "0";
  const isUp = change >= 0;

  const tabs = [
    { key: "chart", label: t.stock.chart },
    { key: "revenue", label: t.stock?.revenue ?? "Revenue" },
    ...(isTWSymbol ? [{ key: "margin", label: t.stock.margin }] : []),
  ];

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start justify-between mb-4 gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-2xl font-bold text-white tracking-tight">{symbol}</h1>
            <button
              onClick={() => watchlist.toggle(symbol, companyInfo?.name ?? symbol, latestPrice?.market ?? "")}
              className="transition-colors duration-200"
              title={watchlist.has(symbol) ? (t.watchlist?.remove ?? "Remove") : (t.watchlist?.add ?? "Add")}
            >
              <svg className="w-5 h-5" fill={watchlist.has(symbol) ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                  className={watchlist.has(symbol) ? "text-yellow-400" : "text-[var(--text-muted)] hover:text-yellow-400"}
                />
              </svg>
            </button>
          </div>

          {/* Price line */}
          <div className="flex items-center gap-3 flex-wrap">
            {latestPrice && (
              <span className={`text-3xl font-bold mono-nums ${isUp ? "text-[var(--stock-up)] glow-red" : "text-[var(--stock-down)] glow-green"}`}>
                {parseFloat(latestPrice.close).toLocaleString()}
              </span>
            )}
            {latestPrice && <ChangeBadge change={change} changePct={changePct} />}
            {companyInfo?.name && (
              <span className="text-[var(--text-muted)] text-sm">{companyInfo.name}</span>
            )}
            {companyInfo?.industry && (
              <Badge variant="blue">{companyInfo.industry}</Badge>
            )}
          </div>
        </div>

        {/* Navigation tabs */}
        <div className="flex items-center gap-2">
          <TabGroup tabs={tabs} active={activeTab} onChange={setActiveTab} size="sm" />
          <Link
            href={`/stocks/${encodeURIComponent(symbol)}/financials`}
            className="px-3 py-1.5 text-xs font-medium rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-[var(--card-hover)] transition-all duration-200"
          >
            {t.stock.financials}
          </Link>
        </div>
      </div>

      {prices.length > 0 ? (
        <>
          {/* Price stats grid */}
          <div className="mb-4 grid grid-cols-2 md:grid-cols-5 gap-2">
            <StatCard label={t.stock.open} value={parseFloat(latestPrice!.open).toLocaleString()} size="sm" />
            <StatCard label={t.stock.close} value={parseFloat(latestPrice!.close).toLocaleString()} size="sm" />
            <StatCard label={t.stock.high} value={parseFloat(latestPrice!.high).toLocaleString()} size="sm" />
            <StatCard label={t.stock.low} value={parseFloat(latestPrice!.low).toLocaleString()} size="sm" />
            <StatCard
              label={t.stock.volume}
              value={latestPrice!.volume.toLocaleString()}
              className="col-span-2 md:col-span-1"
              size="sm"
            />
          </div>

          {/* Chart tab */}
          {activeTab === "chart" && (
            <div className="bg-[var(--background)] border border-[var(--border-subtle)] rounded-lg">
              <div className="flex items-center justify-between px-3 pt-3">
                <h3 className="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider">{t.stock.chart}</h3>
                <TabGroup tabs={TIMEFRAMES} active={timeframe} onChange={setTimeframe} size="sm" />
              </div>
              <div className="p-3">
                <StockChart prices={prices} height={500} />
              </div>
            </div>
          )}

          {/* Margin tab */}
          {activeTab === "margin" && (
            marginLoading ? (
              <LoadingSpinner text={t.stock.loading} size="sm" />
            ) : marginData ? (
              <MarginPanel margin={marginData} t={t} />
            ) : (
              <div className="text-center py-12">
                <p className="text-[var(--text-muted)] text-sm">{t.stock.noData}</p>
              </div>
            )
          )}

          {/* Revenue tab */}
          {activeTab === "revenue" && (
            revenueLoading ? (
              <LoadingSpinner text={t.stock.loading} size="sm" />
            ) : revenueData ? (
              <RevenuePanel revenue={revenueData} t={t} />
            ) : (
              <div className="text-center py-12">
                <p className="text-[var(--text-muted)] text-sm">{t.stock.noData}</p>
              </div>
            )
          )}

          {/* Quick links */}
          <div className="mt-4 flex flex-wrap gap-1.5 text-xs">
            <Link
              href="/low-base"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-[var(--card-hover)] transition-colors duration-150"
            >
              {t.lowBase?.viewDetail ?? "View Low-Base Score"}
            </Link>
          </div>
        </>
      ) : (
        <div className="text-center py-16">
          <p className="text-[var(--text-muted)] text-sm">{t.stock.noData}</p>
        </div>
      )}
    </div>
  );
}
