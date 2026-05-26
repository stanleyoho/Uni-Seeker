"use client";

import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { useLowBaseRanking } from "@/hooks/use-market-data";
import { GlassPanel, KpiCard, ClippedButton } from "@/components/stratos/primitives";
import { LoadingSpinner } from "@/components/ui/loading";
import { getErrorMessage } from "@/lib/type-guards";
import { AmbientBackground } from "@/components/stratos/ambient";

function formatPct(v: number | string | null): string {
  if (v == null) return "-";
  return `${(Number(v) * 100).toFixed(1)}%`;
}

function formatNum(v: number | string | null, decimals = 2): string {
  if (v == null) return "-";
  return Number(v).toFixed(decimals);
}

function scoreColor(score: number | string): string {
  const n = Number(score);
  if (n >= 80) return "var(--stock-up)";
  if (n >= 60) return "var(--accent-cyan, #00E5FF)";
  if (n >= 40) return "var(--foreground)";
  return "var(--text-secondary)";
}

export default function LowBasePage() {
  const { t } = useI18n();
  const lb = t.lowBase;

  const { data, isLoading: loading, error: queryError, refetch: load } = useLowBaseRanking(20);
  const error = queryError ? getErrorMessage(queryError) : null;

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        
        {/* Header row */}
        <div className="flex items-end justify-between mb-6 border-b border-[var(--border-subtle)] pb-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              {lb.title}
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              {lb.subtitle}
            </p>
          </div>
          <ClippedButton
            variant="red-solid"
            size="sm"
            onClick={() => load()}
            disabled={loading}
          >
            {loading ? "INITIALIZING SCAN..." : "REFRESH DATA"}
          </ClippedButton>
        </div>

        {/* Summary KPI cards */}
        {data && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <KpiCard
              label="TOTAL SCANNED"
              value={String(data.total_scanned)}
              delta="STOCKS"
              direction="flat"
            />
            <KpiCard
              label="QUALIFIED"
              value={String(data.total_qualified)}
              delta="PASSED FILTERS"
              direction="up"
            />
            <KpiCard
              label="HIT RATE"
              value={data.total_scanned > 0 ? `${((data.total_qualified / data.total_scanned) * 100).toFixed(1)}%` : "-"}
              delta="SUCCESS RATIO"
              direction="flat"
            />
            <KpiCard
              label="AVG SCORE"
              value={data.results.length > 0 ? (data.results.reduce((s, r) => s + Number(r.total_score), 0) / data.results.length).toFixed(1) : "-"}
              delta="TOP RANKINGS"
              direction="up"
            />
          </div>
        )}

        {loading ? (
          <div className="py-20 flex justify-center"><LoadingSpinner /></div>
        ) : error ? (
          <GlassPanel className="py-20 text-center">
            <p className="text-red-400 font-bold mb-4">ERROR: {error.toUpperCase()}</p>
            <ClippedButton variant="red-ghost" size="sm" onClick={() => load()}>RETRY</ClippedButton>
          </GlassPanel>
        ) : (
          <>
            {/* Desktop Table View */}
            <GlassPanel title="LEADERBOARD - LOW BASE CANDIDATES" noPadding>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Rank</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Security</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-center">Score</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-center">Valuation</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-center">Position</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-center">Quality</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">PE %</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">MA240</th>
                      <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">PEG</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data?.results.map((row, idx) => (
                      <tr
                        key={row.symbol}
                        className="border-b border-[var(--border-subtle)] hover:bg-[var(--card-hover)] transition-all group"
                      >
                        <td className="px-4 py-3 text-[11px] font-bold text-[var(--text-muted)] tabular-nums">
                          #{String(idx + 1).padStart(2, '0')}
                        </td>
                        <td className="px-4 py-3">
                          <Link href={`/stocks/${encodeURIComponent(row.symbol)}`} className="flex flex-col">
                            <span className="text-sm font-bold text-[var(--foreground)] group-hover:text-[var(--accent-cyan)] transition-colors">
                              {row.symbol}
                            </span>
                            <span className="text-[10px] text-[var(--text-muted)] font-medium">
                              {row.name.toUpperCase()}
                            </span>
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className="text-sm font-bold tabular-nums" style={{ color: scoreColor(row.total_score) }}>
                            {row.total_score}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center text-xs font-bold tabular-nums text-[var(--text-secondary)]">
                          {row.valuation_score}
                        </td>
                        <td className="px-4 py-3 text-center text-xs font-bold tabular-nums text-[var(--text-secondary)]">
                          {row.price_position_score}
                        </td>
                        <td className="px-4 py-3 text-center text-xs font-bold tabular-nums text-[var(--text-secondary)]">
                          {row.quality_score}
                        </td>
                        <td className="px-4 py-3 text-right text-[11px] font-bold tabular-nums text-[var(--text-secondary)]">
                          {formatPct(row.pe_percentile ?? null)}
                        </td>
                        <td className="px-4 py-3 text-right text-[11px] font-bold tabular-nums text-[var(--text-secondary)]">
                          {formatPct(row.ma240_deviation ?? null)}
                        </td>
                        <td className="px-4 py-3 text-right text-[11px] font-bold tabular-nums text-[var(--text-secondary)]">
                          {formatNum(row.peg ?? null)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassPanel>
          </>
        )}
      </main>
    </div>
  );
}
