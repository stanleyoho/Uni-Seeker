"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { StockChart } from "@/components/charts/stock-chart";
import { fetchPrices, type StockPrice } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

function PriceStatCard({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={`bg-[#1a2332] border border-[#1e293b] rounded-xl p-4 transition-all duration-200 hover:border-[#253449] ${className || ""}`}>
      <span className="text-[#64748b] text-xs uppercase tracking-wider font-medium">{label}</span>
      <p className="text-xl font-semibold text-white mt-1 font-mono">{value}</p>
    </div>
  );
}

export default function StockDetailPage() {
  const { t } = useI18n();
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [prices, setPrices] = useState<StockPrice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"chart" | "financials">("chart");

  useEffect(() => {
    let cancelled = false;
    fetchPrices(symbol, 120)
      .then((res) => {
        if (!cancelled) setPrices(res.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-[#1e293b] border-t-blue-500 rounded-full animate-spin" />
          <span className="text-[#94a3b8]">{t.stock.loading}</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 text-center">
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6 max-w-md mx-auto">
          <p className="text-red-400">{error}</p>
        </div>
      </div>
    );
  }

  const latestPrice = prices.length > 0 ? prices[0] : null;
  const change = latestPrice ? parseFloat(latestPrice.change) : 0;
  const changePct = latestPrice ? latestPrice.change_percent : "0";
  const isUp = change >= 0;

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 gap-4">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">{symbol}</h1>
            {latestPrice && (
              <div className="flex items-center gap-3 mt-1">
                <span className="text-2xl font-mono font-bold text-white">
                  {parseFloat(latestPrice.close).toLocaleString()}
                </span>
                <span
                  className={`text-sm font-semibold px-2.5 py-1 rounded-lg ${
                    isUp
                      ? "text-red-400 bg-red-500/10"
                      : "text-green-400 bg-green-500/10"
                  }`}
                >
                  {isUp ? "+" : ""}
                  {change.toFixed(2)} ({changePct}%)
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-[#111827] p-1 rounded-xl">
          <button
            onClick={() => setActiveTab("chart")}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${
              activeTab === "chart"
                ? "bg-blue-600 text-white shadow-lg shadow-blue-600/20"
                : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]"
            }`}
          >
            {t.stock.chart}
          </button>
          <Link
            href={`/stocks/${encodeURIComponent(symbol)}/financials`}
            className="px-4 py-2 text-sm font-medium rounded-lg text-[#94a3b8] hover:text-white hover:bg-[#1e293b] transition-all duration-200"
          >
            {t.stock.financials}
          </Link>
        </div>
      </div>

      {prices.length > 0 ? (
        <>
          {/* Price stats grid */}
          <div className="mb-6 grid grid-cols-2 md:grid-cols-5 gap-3">
            <PriceStatCard label={t.stock.open} value={parseFloat(latestPrice!.open).toLocaleString()} />
            <PriceStatCard label={t.stock.close} value={parseFloat(latestPrice!.close).toLocaleString()} />
            <PriceStatCard label={t.stock.high} value={parseFloat(latestPrice!.high).toLocaleString()} />
            <PriceStatCard label={t.stock.low} value={parseFloat(latestPrice!.low).toLocaleString()} />
            <PriceStatCard
              label={t.stock.volume}
              value={latestPrice!.volume.toLocaleString()}
              className="col-span-2 md:col-span-1"
            />
          </div>

          {/* Low-Base Score link */}
          <div className="mb-6">
            <Link
              href="/low-base"
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-[#1a2332] border border-[#1e293b] rounded-xl text-sm text-[#94a3b8] hover:text-white hover:border-[#3b82f6]/40 transition-all duration-200"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              {t.lowBase?.viewDetail ?? "View Low-Base Score"}
            </Link>
          </div>

          {/* Chart container */}
          <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-4 shadow-xl shadow-black/20">
            <StockChart prices={prices} height={500} />
          </div>
        </>
      ) : (
        <div className="text-center py-20">
          <p className="text-[#64748b] text-lg">{t.stock.noData}</p>
        </div>
      )}
    </div>
  );
}
