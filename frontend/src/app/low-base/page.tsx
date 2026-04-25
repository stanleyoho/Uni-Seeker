"use client";

import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { type LowBaseScore } from "@/lib/api-client";
import { useLowBaseRanking } from "@/hooks/use-market-data";
import { StatCard } from "@/components/ui/stat-card";
import { ScoreBadge } from "@/components/ui/badge";
import { ScoreBar } from "@/components/ui/score-bar";
import { LoadingSpinner } from "@/components/ui/loading";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
import { DataTable, type Column } from "@/components/ui/data-table";

function formatPct(v: number | null): string {
  if (v == null) return "-";
  return `${(v * 100).toFixed(1)}%`;
}

function formatNum(v: number | null, decimals = 2): string {
  if (v == null) return "-";
  return v.toFixed(decimals);
}

export default function LowBasePage() {
  const { t } = useI18n();
  const lb = t.lowBase;

  const { data, isLoading: loading, error: queryError, refetch: load } = useLowBaseRanking(20);
  const error = queryError ? (queryError as Error).message : null;

  const columns: Column<LowBaseScore>[] = [
    {
      key: "rank",
      header: lb.rank,
      width: "w-10",
      render: (_row, idx) => (
        <span className="text-[var(--text-muted)] mono-nums text-[10px]">#{idx + 1}</span>
      ),
    },
    {
      key: "stock",
      header: lb.stock,
      render: (row) => (
        <div>
          <Link
            href={`/stocks/${encodeURIComponent(row.symbol)}`}
            className="text-white font-semibold text-xs hover:text-[var(--accent-blue)] transition-colors duration-150"
          >
            {row.symbol}
          </Link>
          <span className="text-[var(--text-muted)] text-[10px] ml-1.5">{row.name}</span>
        </div>
      ),
    },
    {
      key: "score",
      header: lb.score,
      align: "center",
      width: "w-20",
      render: (row) => <ScoreBadge score={row.total_score} />,
    },
    {
      key: "details",
      header: lb.details,
      width: "w-48",
      render: (row) => (
        <div className="space-y-0.5">
          <ScoreBar label={lb.valuationScore} value={row.valuation_score} />
          <ScoreBar label={lb.priceScore} value={row.price_position_score} />
          <ScoreBar label={lb.qualityScore} value={row.quality_score} />
        </div>
      ),
    },
    {
      key: "pe",
      header: lb.pePercentile,
      align: "right",
      width: "w-24",
      render: (row) => (
        <span className="text-[var(--text-secondary)] mono-nums text-[10px]">{formatPct(row.pe_percentile)}</span>
      ),
    },
    {
      key: "ma",
      header: lb.maDeviation,
      align: "right",
      width: "w-24",
      render: (row) => (
        <span className="text-[var(--text-secondary)] mono-nums text-[10px]">{formatPct(row.ma240_deviation)}</span>
      ),
    },
    {
      key: "peg",
      header: lb.peg,
      align: "right",
      width: "w-16",
      render: (row) => (
        <span className="text-[var(--text-secondary)] mono-nums text-[10px]">{formatNum(row.peg)}</span>
      ),
    },
  ];

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-white tracking-tight">{lb.title}</h1>
          <p className="text-[var(--text-muted)] text-xs mt-0.5">{lb.subtitle}</p>
        </div>
        <button
          onClick={() => load()}
          disabled={loading}
          className="self-start md:self-auto px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--accent-blue)] hover:bg-[var(--accent-blue-hover)] text-white transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? lb.scanning : "Refresh"}
        </button>
      </div>

      {/* Stats cards */}
      {data && (
        <div className="grid grid-cols-2 gap-2 mb-4">
          <StatCard label={lb.scanned} value={data.total_scanned} size="sm" />
          <StatCard label={lb.qualified} value={data.total_qualified} size="sm" />
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
            <Link
              key={item.symbol}
              href={`/stocks/${encodeURIComponent(item.symbol)}`}
              className="block bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-3 hover:bg-[var(--card-hover)] transition-colors duration-150"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-[var(--text-muted)] text-xs mono-nums w-5">#{idx + 1}</span>
                  <div>
                    <span className="text-white font-semibold text-sm">{item.symbol}</span>
                    <span className="text-[var(--text-muted)] text-[10px] ml-1.5">{item.name}</span>
                  </div>
                </div>
                <ScoreBadge score={item.total_score} />
              </div>
              <div className="space-y-1">
                <ScoreBar label={lb.valuationScore} value={item.valuation_score} />
                <ScoreBar label={lb.priceScore} value={item.price_position_score} />
                <ScoreBar label={lb.qualityScore} value={item.quality_score} />
              </div>
              <div className="mt-2 flex gap-3 text-[10px] text-[var(--text-muted)] mono-nums">
                <span>PE%: {formatPct(item.pe_percentile)}</span>
                <span>MA240: {formatPct(item.ma240_deviation)}</span>
                <span>PEG: {formatNum(item.peg)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Desktop table */}
      {data && data.results.length > 0 && (
        <div className="hidden md:block bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg overflow-hidden">
          <DataTable
            columns={columns}
            data={data.results}
            rowKey={(row) => row.symbol}
            compact
          />
        </div>
      )}
    </div>
  );
}
