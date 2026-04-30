"use client";

import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { type LowBaseScore } from "@/lib/api-client";
import { useLowBaseRanking } from "@/hooks/use-market-data";
import { GlassPanel, KpiCard, ClippedButton } from "@/components/stratos/primitives";
import { ScoreBadge } from "@/components/ui/badge";
import { ScoreBar } from "@/components/ui/score-bar";
import { LoadingSpinner } from "@/components/ui/loading";
import { getErrorMessage } from "@/lib/type-guards";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";

function formatPct(v: number | null): string {
  if (v == null) return "-";
  return `${(v * 100).toFixed(1)}%`;
}

function formatNum(v: number | null, decimals = 2): string {
  if (v == null) return "-";
  return v.toFixed(decimals);
}

function scoreColor(score: number): string {
  if (score >= 80) return "var(--stock-up)";
  if (score >= 60) return "var(--accent-cyan, #00E5FF)";
  if (score >= 40) return "var(--foreground)";
  return "var(--text-secondary)";
}

export default function LowBasePage() {
  const { t } = useI18n();
  const lb = t.lowBase;

  const { data, isLoading: loading, error: queryError, refetch: load } = useLowBaseRanking(20);
  const error = queryError ? getErrorMessage(queryError) : null;

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-[var(--foreground)] tracking-tight">
            {lb.title}
          </h1>
          <p className="text-[var(--text-secondary)] text-xs mt-0.5">{lb.subtitle}</p>
        </div>
        <ClippedButton
          variant="red-solid"
          size="sm"
          onClick={() => load()}
          disabled={loading}
        >
          {loading ? lb.scanning : "Refresh"}
        </ClippedButton>
      </div>

      {/* KPI Cards */}
      {data && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <KpiCard
            label={lb.scanned}
            value={String(data.total_scanned)}
            delta="掃描股票"
            direction="flat"
          />
          <KpiCard
            label={lb.qualified}
            value={String(data.total_qualified)}
            delta="符合資格"
            direction="flat"
          />
        </div>
      )}

      {loading && <LoadingSpinner text={lb.scanning} size="sm" />}

      {error && !loading && <ErrorState message={error} onRetry={() => load()} />}

      {data && data.results.length === 0 && !loading && (
        <EmptyState message={lb.noData} />
      )}

      {/* Mobile cards */}
      {data && data.results.length > 0 && (
        <div className="md:hidden space-y-2">
          {data.results.map((item, idx) => (
            <GlassPanel key={item.symbol} noPadding>
              <Link
                href={`/stocks/${encodeURIComponent(item.symbol)}`}
                className="block p-3 transition-colors duration-150"
                style={{ borderRadius: "var(--glass-radius, 0)" }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--card-hover)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[var(--text-secondary)] text-xs mono-nums w-5">
                      #{idx + 1}
                    </span>
                    <div>
                      <span className="text-[var(--foreground)] font-semibold text-sm">
                        {item.symbol}
                      </span>
                      <span className="text-[var(--text-secondary)] text-[10px] ml-1.5">
                        {item.name}
                      </span>
                    </div>
                  </div>
                  <ScoreBadge score={item.total_score} />
                </div>
                <div className="space-y-1">
                  <ScoreBar label={lb.valuationScore} value={item.valuation_score} />
                  <ScoreBar label={lb.priceScore} value={item.price_position_score} />
                  <ScoreBar label={lb.qualityScore} value={item.quality_score} />
                </div>
                <div className="mt-2 flex gap-3 text-[10px] text-[var(--text-secondary)] mono-nums">
                  <span>PE%: {formatPct(item.pe_percentile)}</span>
                  <span>MA240: {formatPct(item.ma240_deviation)}</span>
                  <span>PEG: {formatNum(item.peg)}</span>
                </div>
              </Link>
            </GlassPanel>
          ))}
        </div>
      )}

      {/* Desktop table */}
      {data && data.results.length > 0 && (
        <GlassPanel noPadding className="hidden md:block overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr
                style={{
                  borderBottom: "1px solid var(--border-color)",
                  background: "rgba(255,255,255,0.02)",
                }}
              >
                <th className="text-left px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider">
                  {lb.rank}
                </th>
                <th className="text-left px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider">
                  {lb.stock}
                </th>
                <th className="text-center px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider">
                  {lb.score}
                </th>
                <th className="text-left px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-48">
                  {lb.details}
                </th>
                <th className="text-right px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider">
                  {lb.pePercentile}
                </th>
                <th className="text-right px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider">
                  {lb.maDeviation}
                </th>
                <th className="text-right px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider">
                  {lb.peg}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row, idx) => (
                <tr
                  key={row.symbol}
                  className="transition-colors duration-150 cursor-pointer"
                  style={{ borderBottom: "1px solid var(--border-color)" }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = "var(--card-hover)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = "transparent";
                  }}
                >
                  <td className="px-3 py-2">
                    <span className="text-[var(--text-secondary)] mono-nums text-[10px]">
                      #{idx + 1}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/stocks/${encodeURIComponent(row.symbol)}`}
                      className="text-[var(--foreground)] font-semibold text-xs hover:text-[var(--accent-cyan)] transition-colors duration-150"
                    >
                      {row.symbol}
                    </Link>
                    <span className="text-[var(--text-secondary)] text-[10px] ml-1.5">
                      {row.name}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span
                      className="mono-nums font-bold text-sm"
                      style={{ color: scoreColor(row.total_score) }}
                    >
                      {row.total_score}
                    </span>
                  </td>
                  <td className="px-3 py-2 w-48">
                    <div className="space-y-0.5">
                      <ScoreBar label={lb.valuationScore} value={row.valuation_score} />
                      <ScoreBar label={lb.priceScore} value={row.price_position_score} />
                      <ScoreBar label={lb.qualityScore} value={row.quality_score} />
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className="text-[var(--text-secondary)] mono-nums text-[10px]">
                      {formatPct(row.pe_percentile)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className="text-[var(--text-secondary)] mono-nums text-[10px]">
                      {formatPct(row.ma240_deviation)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <span className="text-[var(--text-secondary)] mono-nums text-[10px]">
                      {formatNum(row.peg)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassPanel>
      )}
    </div>
  );
}
