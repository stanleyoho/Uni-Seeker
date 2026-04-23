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
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const color = scoreColor(score, 100);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke="#374151"
          strokeWidth="10"
        />
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          transform="rotate(-90 70 70)"
          className="transition-all duration-700"
        />
        <text
          x="70"
          y="66"
          textAnchor="middle"
          className="fill-white text-3xl font-bold"
          fontSize="32"
        >
          {score}
        </text>
        <text
          x="70"
          y="88"
          textAnchor="middle"
          className="fill-gray-400"
          fontSize="12"
        >
          / 100
        </text>
      </svg>
      <span className="text-sm text-gray-400">{label}</span>
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
      <span className="w-28 text-sm text-gray-300 shrink-0">{label}</span>
      <div className="flex-1 h-3 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-sm font-mono w-14 text-right" style={{ color }}>
        {score.toFixed(1)}/{max}
      </span>
    </div>
  );
}

function RatiosTable({ ratios }: { ratios: FinancialRatios }) {
  const items: { label: string; value: string }[] = [
    { label: "Gross Margin", value: formatPct(ratios.gross_margin) },
    { label: "Operating Margin", value: formatPct(ratios.operating_margin) },
    { label: "Net Margin", value: formatPct(ratios.net_margin) },
    { label: "ROE", value: formatPct(ratios.roe) },
    { label: "ROA", value: formatPct(ratios.roa) },
    { label: "Current Ratio", value: formatNumber(ratios.current_ratio) },
    { label: "Debt Ratio", value: formatNumber(ratios.debt_ratio) },
    { label: "Revenue Growth", value: formatPct(ratios.revenue_growth) },
    { label: "Net Income Growth", value: formatPct(ratios.net_income_growth) },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="bg-gray-800 rounded-lg p-4 border border-gray-700"
        >
          <div className="text-xs text-gray-400 mb-1">{item.label}</div>
          <div className="text-lg font-semibold">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

function QuarterlyTrend({ ratios }: { ratios: FinancialRatios[] }) {
  if (ratios.length < 2) return null;

  const sorted = [...ratios].sort(
    (a, b) => a.period.localeCompare(b.period),
  );

  const metrics: { key: keyof FinancialRatios; label: string; isPct: boolean }[] = [
    { key: "gross_margin", label: "Gross Margin", isPct: true },
    { key: "operating_margin", label: "Operating Margin", isPct: true },
    { key: "net_margin", label: "Net Margin", isPct: true },
    { key: "roe", label: "ROE", isPct: true },
    { key: "roa", label: "ROA", isPct: true },
    { key: "current_ratio", label: "Current Ratio", isPct: false },
    { key: "debt_ratio", label: "Debt Ratio", isPct: false },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-700">
            <th className="text-left py-2 px-3 text-gray-400 font-medium">
              Metric
            </th>
            {sorted.map((r) => (
              <th
                key={r.period}
                className="text-right py-2 px-3 text-gray-400 font-medium"
              >
                {r.period}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.key} className="border-b border-gray-800">
              <td className="py-2 px-3 text-gray-300">{m.label}</td>
              {sorted.map((r) => {
                const val = r[m.key] as number | null;
                return (
                  <td key={r.period} className="text-right py-2 px-3 font-mono">
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

  if (loading) return <div className="p-8 text-center">Loading financial data...</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error}</div>;
  if (!data) return <div className="p-8 text-center text-gray-400">No data available</div>;

  const latestScore =
    data.health_scores.length > 0 ? data.health_scores[0] : null;
  const latestRatios = data.ratios.length > 0 ? data.ratios[0] : null;

  return (
    <div className="p-4 max-w-6xl mx-auto">
      {/* Header with navigation tabs */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{symbol}</h1>
        <div className="flex gap-2">
          <Link
            href={`/stocks/${encodeURIComponent(symbol)}`}
            className="px-4 py-2 text-sm rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 transition"
          >
            Chart
          </Link>
          <span className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white">
            Financials
          </span>
        </div>
      </div>

      {/* Health Score Section */}
      {latestScore && (
        <div className="bg-gray-800 rounded-xl p-6 mb-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">
            Health Score
            <span className="text-sm text-gray-400 ml-2 font-normal">
              Period: {latestScore.period}
            </span>
          </h2>
          <div className="flex flex-col md:flex-row items-center gap-8">
            <CircularScore
              score={Math.round(latestScore.total_score)}
              label="Overall Health"
            />
            <div className="flex-1 w-full space-y-3">
              <CategoryBar
                label="Profitability"
                score={latestScore.profitability_score}
                max={25}
              />
              <CategoryBar
                label="Efficiency"
                score={latestScore.efficiency_score}
                max={25}
              />
              <CategoryBar
                label="Leverage"
                score={latestScore.leverage_score}
                max={25}
              />
              <CategoryBar
                label="Growth"
                score={latestScore.growth_score}
                max={25}
              />
            </div>
          </div>
        </div>
      )}

      {/* Key Ratios */}
      {latestRatios && (
        <div className="bg-gray-800 rounded-xl p-6 mb-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">
            Key Ratios
            <span className="text-sm text-gray-400 ml-2 font-normal">
              Period: {latestRatios.period}
            </span>
          </h2>
          <RatiosTable ratios={latestRatios} />
        </div>
      )}

      {/* Quarterly Trend */}
      {data.ratios.length > 1 && (
        <div className="bg-gray-800 rounded-xl p-6 mb-6 border border-gray-700">
          <h2 className="text-lg font-semibold mb-4">Quarterly Trend</h2>
          <QuarterlyTrend ratios={data.ratios} />
        </div>
      )}

      {/* No data fallback */}
      {!latestScore && !latestRatios && (
        <div className="text-center text-gray-400 py-12">
          No financial analysis data available for {symbol}.
        </div>
      )}
    </div>
  );
}
