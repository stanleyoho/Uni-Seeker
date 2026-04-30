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
      {/* Header row */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1
            className="text-lg font-bold tracking-tight"
            style={{ color: "var(--foreground)" }}
          >
            {lb.title}
          </h1>
          <p className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
            {lb.subtitle}
          </p>
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

      {/* Summary KPI cards */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
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
          <KpiCard
            label="合格率"
            value={data.total_scanned > 0 ? `${((data.total_qualified / data.total_scanned) * 100).toFixed(1)}%` : "-"}
            delta="qualified / scanned"
            direction="flat"
          />
          <KpiCard
            label="平均分數"
            value={data.results.length > 0 ? (data.results.reduce((s, r) => s + r.total_score, 0) / data.results.length).toFixed(1) : "-"}
            delta="top results"
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

      {/* Full-width dense desktop table */}
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
                <th className="text-left px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-10">
                  {lb.rank}
                </th>
                <th className="text-left px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider">
                  {lb.stock}
                </th>
                <th className="text-center px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-16">
                  {lb.score}
                </th>
                <th className="text-center px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-16">
                  {lb.valuationScore}
                </th>
                <th className="text-center px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-16">
                  {lb.priceScore}
                </th>
                <th className="text-center px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-16">
                  {lb.qualityScore}
                </th>
                <th className="text-left px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-36">
                  {lb.details}
                </th>
                <th className="text-right px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-16">
                  {lb.pePercentile}
                </th>
                <th className="text-right px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-16">
                  {lb.maDeviation}
                </th>
                <th className="text-right px-3 py-2 text-[var(--text-secondary)] font-semibold text-[10px] uppercase tracking-wider w-14">
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
                    <span className="text-[var(--text-muted)] mono-nums text-[10px]">
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
                  <td className="px-3 py-2 text-center">
                    <span className="mono-nums text-[11px]" style={{ color: scoreColor(row.valuation_score) }}>
                      {row.valuation_score}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span className="mono-nums text-[11px]" style={{ color: scoreColor(row.price_position_score) }}>
                      {row.price_position_score}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span className="mono-nums text-[11px]" style={{ color: scoreColor(row.quality_score) }}>
                      {row.quality_score}
                    </span>
                  </td>
                  <td className="px-3 py-2 w-36">
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
