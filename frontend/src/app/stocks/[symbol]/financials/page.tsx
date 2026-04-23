"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchFinancialAnalysis,
  type FullAnalysis,
  type FinancialRatios,
  type HealthScore,
} from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

function scoreColor(score: number, max: number): string {
  const pct = (score / max) * 100;
  if (pct < 40) return "#ef4444";
  if (pct < 70) return "#eab308";
  return "#22c55e";
}

function formatPct(value: number | null): string {
  if (value === null || value === undefined) return "N/A";
  return `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value: number | null): string {
  if (value === null || value === undefined) return "N/A";
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function CircularScore({ score, label }: { score: number; label: string }) {
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const color = scoreColor(score, 100);

  return (
    <div className="flex flex-col items-center gap-3">
      <svg width="160" height="160" viewBox="0 0 160 160">
        {/* Background track */}
        <circle
          cx="80"
          cy="80"
          r={radius}
          fill="none"
          stroke="#1e293b"
          strokeWidth="12"
        />
        {/* Progress arc */}
        <circle
          cx="80"
          cy="80"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          transform="rotate(-90 80 80)"
          className="transition-all duration-1000"
          style={
            { "--ring-circumference": circumference } as React.CSSProperties
          }
        />
        {/* Glow effect */}
        <circle
          cx="80"
          cy="80"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          transform="rotate(-90 80 80)"
          opacity="0.3"
          filter="blur(4px)"
        />
        {/* Score text */}
        <text
          x="80"
          y="74"
          textAnchor="middle"
          className="fill-white font-bold"
          fontSize="36"
          fontFamily="monospace"
        >
          {score}
        </text>
        <text
          x="80"
          y="98"
          textAnchor="middle"
          fill="#64748b"
          fontSize="13"
        >
          / 100
        </text>
      </svg>
      <span className="text-sm text-[#94a3b8] font-medium">{label}</span>
    </div>
  );
}

function CategoryBar({
  label,
  score,
  max,
}: {
  label: string;
  score: number;
  max: number;
}) {
  const pct = (score / max) * 100;
  const color = scoreColor(score, max);

  return (
    <div className="flex items-center gap-3">
      <span className="w-28 text-sm text-[#94a3b8] shrink-0 font-medium">{label}</span>
      <div className="flex-1 h-2.5 bg-[#111827] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-sm font-mono w-16 text-right font-medium" style={{ color }}>
        {score.toFixed(1)}/{max}
      </span>
    </div>
  );
}

function RatiosTable({ ratios, t }: { ratios: FinancialRatios; t: ReturnType<typeof useI18n>["t"] }) {
  const items: { label: string; value: string }[] = [
    { label: t.financial.grossMargin, value: formatPct(ratios.gross_margin) },
    { label: t.financial.operatingMargin, value: formatPct(ratios.operating_margin) },
    { label: t.financial.netMargin, value: formatPct(ratios.net_margin) },
    { label: t.financial.roe, value: formatPct(ratios.roe) },
    { label: t.financial.roa, value: formatPct(ratios.roa) },
    { label: t.financial.currentRatio, value: formatNumber(ratios.current_ratio) },
    { label: t.financial.debtRatio, value: formatNumber(ratios.debt_ratio) },
    { label: t.financial.revenueGrowth, value: formatPct(ratios.revenue_growth) },
    { label: t.financial.netIncomeGrowth, value: formatPct(ratios.net_income_growth) },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {items.map((item, i) => {
        const numVal = parseFloat(item.value);
        const isPositive = !isNaN(numVal) && numVal > 0;
        const isNegative = !isNaN(numVal) && numVal < 0;

        return (
          <div
            key={item.label}
            className="bg-[#111827] rounded-xl p-4 border border-[#1e293b] transition-all duration-200 hover:border-[#253449]"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">{item.label}</div>
            <div className={`text-lg font-semibold font-mono ${
              isPositive ? "text-green-400" : isNegative ? "text-red-400" : "text-white"
            }`}>
              {item.value}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function QuarterlyTrend({ ratios, t }: { ratios: FinancialRatios[]; t: ReturnType<typeof useI18n>["t"] }) {
  if (ratios.length < 2) return null;

  const sorted = [...ratios].sort(
    (a, b) => a.period.localeCompare(b.period),
  );

  const metrics: { key: keyof FinancialRatios; label: string; isPct: boolean }[] = [
    { key: "gross_margin", label: t.financial.grossMargin, isPct: true },
    { key: "operating_margin", label: t.financial.operatingMargin, isPct: true },
    { key: "net_margin", label: t.financial.netMargin, isPct: true },
    { key: "roe", label: t.financial.roe, isPct: true },
    { key: "roa", label: t.financial.roa, isPct: true },
    { key: "current_ratio", label: t.financial.currentRatio, isPct: false },
    { key: "debt_ratio", label: t.financial.debtRatio, isPct: false },
  ];

  return (
    <div className="overflow-x-auto rounded-xl border border-[#1e293b]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[#111827]">
            <th className="text-left py-3 px-4 text-[#64748b] text-xs uppercase tracking-wider font-medium">
              {t.financial.metric}
            </th>
            {sorted.map((r) => (
              <th
                key={r.period}
                className="text-right py-3 px-4 text-[#64748b] text-xs uppercase tracking-wider font-medium"
              >
                {r.period}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((m, i) => (
            <tr
              key={m.key}
              className={`border-t border-[#1e293b] transition-colors duration-150 hover:bg-[#1e293b] ${
                i % 2 === 0 ? "bg-[#1a2332]" : "bg-[#111827]/50"
              }`}
            >
              <td className="py-3 px-4 text-[#94a3b8] font-medium">{m.label}</td>
              {sorted.map((r) => {
                const val = r[m.key] as number | null;
                return (
                  <td key={r.period} className="text-right py-3 px-4 font-mono text-white">
                    {m.isPct ? formatPct(val) : formatNumber(val)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FinancialsPage() {
  const { t } = useI18n();
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [data, setData] = useState<FullAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFinancialAnalysis(symbol)
      .then((res) => {
        if (!cancelled) setData(res);
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
          <span className="text-[#94a3b8]">{t.financial.loadingFinancial}</span>
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
  if (!data) return <div className="p-8 text-center text-[#64748b]">{t.stock.noData}</div>;

  const latestScore =
    data.health_scores.length > 0 ? data.health_scores[0] : null;
  const latestRatios = data.ratios.length > 0 ? data.ratios[0] : null;

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto animate-fade-in">
      {/* Header with navigation tabs */}
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-6 gap-4">
        <h1 className="text-3xl font-bold text-white tracking-tight">{symbol}</h1>
        <div className="flex gap-1 bg-[#111827] p-1 rounded-xl">
          <Link
            href={`/stocks/${encodeURIComponent(symbol)}`}
            className="px-4 py-2 text-sm font-medium rounded-lg text-[#94a3b8] hover:text-white hover:bg-[#1e293b] transition-all duration-200"
          >
            {t.stock.chart}
          </Link>
          <span className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white shadow-lg shadow-blue-600/20">
            {t.stock.financials}
          </span>
        </div>
      </div>

      {/* Health Score Section */}
      {latestScore && (
        <div className="bg-[#1a2332] rounded-2xl p-6 mb-6 border border-[#1e293b]">
          <div className="flex items-center gap-3 mb-5">
            <h2 className="text-lg font-semibold text-white">
              {t.financial.healthScore}
            </h2>
            <span className="text-xs text-[#64748b] bg-[#111827] rounded-lg px-2.5 py-1 border border-[#1e293b]">
              {t.financial.period}: {latestScore.period}
            </span>
          </div>
          <div className="flex flex-col md:flex-row items-center gap-8">
            <CircularScore
              score={Math.round(latestScore.total_score)}
              label={t.financial.overallHealth}
            />
            <div className="flex-1 w-full space-y-4">
              <CategoryBar
                label={t.financial.profitability}
                score={latestScore.profitability_score}
                max={25}
              />
              <CategoryBar
                label={t.financial.efficiency}
                score={latestScore.efficiency_score}
                max={25}
              />
              <CategoryBar
                label={t.financial.leverage}
                score={latestScore.leverage_score}
                max={25}
              />
              <CategoryBar
                label={t.financial.growth}
                score={latestScore.growth_score}
                max={25}
              />
            </div>
          </div>
        </div>
      )}

      {/* Key Ratios */}
      {latestRatios && (
        <div className="bg-[#1a2332] rounded-2xl p-6 mb-6 border border-[#1e293b]">
          <div className="flex items-center gap-3 mb-5">
            <h2 className="text-lg font-semibold text-white">
              {t.financial.keyRatios}
            </h2>
            <span className="text-xs text-[#64748b] bg-[#111827] rounded-lg px-2.5 py-1 border border-[#1e293b]">
              {t.financial.period}: {latestRatios.period}
            </span>
          </div>
          <RatiosTable ratios={latestRatios} t={t} />
        </div>
      )}

      {/* Quarterly Trend */}
      {data.ratios.length > 1 && (
        <div className="bg-[#1a2332] rounded-2xl p-6 mb-6 border border-[#1e293b]">
          <h2 className="text-lg font-semibold mb-4 text-white">{t.financial.quarterlyTrend}</h2>
          <QuarterlyTrend ratios={data.ratios} t={t} />
        </div>
      )}

      {/* No data fallback */}
      {!latestScore && !latestRatios && (
        <div className="text-center py-20">
          <svg className="w-16 h-16 mx-auto text-[#1e293b] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-[#64748b] text-lg">
            {t.financial.noDataFor.replace("{symbol}", symbol)}
          </p>
        </div>
      )}
    </div>
  );
}
