"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import {
  type FinancialRatios,
} from "@/lib/api-client";
import { useI18n } from "@/i18n/context";
import { LoadingSpinner } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/empty-state";
import { useFinancialAnalysis } from "@/hooks/use-market-data";

function scoreColor(score: number, max: number): string {
  const pct = (score / max) * 100;
  if (pct < 40) return "#ef4444";
  if (pct < 70) return "#eab308";
  return "#22c55e";
}

function scoreGlow(score: number, max: number): string {
  const pct = (score / max) * 100;
  if (pct < 40) return "drop-shadow(0 0 6px rgba(239, 68, 68, 0.4))";
  if (pct < 70) return "drop-shadow(0 0 6px rgba(234, 179, 8, 0.4))";
  return "drop-shadow(0 0 6px rgba(34, 197, 94, 0.4))";
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
  const glow = scoreGlow(score, 100);

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="140" height="140" viewBox="0 0 140 140">
        {/* Background track */}
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.04)"
          strokeWidth="10"
        />
        {/* Glow layer */}
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
          opacity="0.3"
          style={{ filter: "blur(4px)" }}
        />
        {/* Progress arc */}
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
          className="transition-all duration-1000"
          style={
            { "--ring-circumference": circumference, filter: glow } as React.CSSProperties
          }
        />
        {/* Score text */}
        <text
          x="70"
          y="66"
          textAnchor="middle"
          className="fill-white font-bold"
          fontSize="32"
          fontFamily="monospace"
        >
          {score}
        </text>
        <text
          x="70"
          y="86"
          textAnchor="middle"
          fill="#475569"
          fontSize="11"
          fontFamily="monospace"
        >
          / 100
        </text>
      </svg>
      <span className="text-xs text-[var(--text-muted)] font-medium">{label}</span>
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
    <div className="flex items-center gap-2">
      <span className="w-24 text-xs text-[var(--text-secondary)] shrink-0 font-medium">{label}</span>
      <div className="flex-1 h-2 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color, boxShadow: `0 0 6px ${color}40` }}
        />
      </div>
      <span className="text-xs w-14 text-right mono-nums font-medium" style={{ color }}>
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
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
      {items.map((item, i) => {
        const numVal = parseFloat(item.value);
        const isPositive = !isNaN(numVal) && numVal > 0;
        const isNegative = !isNaN(numVal) && numVal < 0;

        return (
          <div
            key={item.label}
            className="bg-[var(--bg-secondary)] rounded-lg p-3 border border-[var(--border-subtle)] transition-colors duration-150 hover:bg-[var(--card-hover)]"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">{item.label}</div>
            <div className={`text-base font-semibold mono-nums ${
              isPositive ? "text-[var(--stock-down)] glow-green" : isNegative ? "text-[var(--stock-up)] glow-red" : "text-white"
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
    <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-[var(--bg-secondary)]">
            <th className="text-left py-2 px-3 text-[var(--text-muted)] text-[10px] uppercase tracking-wider font-medium">
              {t.financial.metric}
            </th>
            {sorted.map((r) => (
              <th
                key={r.period}
                className="text-right py-2 px-3 text-[var(--text-muted)] text-[10px] uppercase tracking-wider font-medium mono-nums"
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
              className={`border-t border-[var(--border-subtle)] transition-colors duration-100 hover:bg-[var(--card-hover)] ${
                i % 2 === 0 ? "bg-[var(--card-bg)]" : "bg-[var(--bg-secondary)]/30"
              }`}
            >
              <td className="py-2 px-3 text-[var(--text-secondary)] font-medium">{m.label}</td>
              {sorted.map((r) => {
                const val = r[m.key] as number | null;
                return (
                  <td key={r.period} className="text-right py-2 px-3 mono-nums text-white">
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
  const { data, isLoading: loading, error: queryError } = useFinancialAnalysis(symbol);
  const error = queryError ? (queryError as Error).message : null;

  if (loading) {
    return <LoadingSpinner text={t.financial.loadingFinancial} fullPage />;
  }
  if (error) {
    return (
      <div className="p-6 max-w-md mx-auto">
        <ErrorState message={error} />
      </div>
    );
  }
  if (!data) return <div className="p-6 text-center text-[var(--text-muted)] text-sm">{t.stock.noData}</div>;

  const latestScore =
    data.health_scores.length > 0 ? data.health_scores[0] : null;
  const latestRatios = data.ratios.length > 0 ? data.ratios[0] : null;

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      {/* Header with navigation tabs */}
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-4 gap-3">
        <h1 className="text-xl md:text-2xl font-bold text-white tracking-tight">{symbol}</h1>
        <div className="flex gap-1 bg-[var(--bg-secondary)] p-0.5 rounded-lg">
          <Link
            href={`/stocks/${encodeURIComponent(symbol)}`}
            className="px-3 py-1.5 text-xs font-medium rounded-md text-[var(--text-secondary)] hover:text-white hover:bg-[var(--card-hover)] transition-all duration-200"
          >
            {t.stock.chart}
          </Link>
          <span className="px-3 py-1.5 text-xs font-medium rounded-md bg-[var(--accent-blue)] text-white">
            {t.stock.financials}
          </span>
        </div>
      </div>

      {/* Health Score Section */}
      {latestScore && (
        <div className="bg-[var(--card-bg)] rounded-lg p-4 mb-4 border border-[var(--border-subtle)]">
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-sm font-semibold text-white">
              {t.financial.healthScore}
            </h2>
            <span className="text-[10px] text-[var(--text-muted)] bg-[var(--bg-secondary)] rounded-md px-2 py-0.5 border border-[var(--border-subtle)] mono-nums">
              {t.financial.period}: {latestScore.period}
            </span>
          </div>
          <div className="flex flex-col md:flex-row items-center gap-6">
            <CircularScore
              score={Math.round(latestScore.total_score)}
              label={t.financial.overallHealth}
            />
            <div className="flex-1 w-full space-y-3">
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
        <div className="bg-[var(--card-bg)] rounded-lg p-4 mb-4 border border-[var(--border-subtle)]">
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-sm font-semibold text-white">
              {t.financial.keyRatios}
            </h2>
            <span className="text-[10px] text-[var(--text-muted)] bg-[var(--bg-secondary)] rounded-md px-2 py-0.5 border border-[var(--border-subtle)] mono-nums">
              {t.financial.period}: {latestRatios.period}
            </span>
          </div>
          <RatiosTable ratios={latestRatios} t={t} />
        </div>
      )}

      {/* Quarterly Trend */}
      {data.ratios.length > 1 && (
        <div className="bg-[var(--card-bg)] rounded-lg p-4 mb-4 border border-[var(--border-subtle)]">
          <h2 className="text-sm font-semibold mb-3 text-white">{t.financial.quarterlyTrend}</h2>
          <QuarterlyTrend ratios={data.ratios} t={t} />
        </div>
      )}

      {/* No data fallback */}
      {!latestScore && !latestRatios && (
        <div className="text-center py-16">
          <p className="text-[var(--text-muted)] text-sm">
            {t.financial.noDataFor.replace("{symbol}", symbol)}
          </p>
        </div>
      )}
    </div>
  );
}
