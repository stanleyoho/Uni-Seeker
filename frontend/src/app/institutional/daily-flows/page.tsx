"use client";

import { useState, useMemo } from "react";
import { useI18n } from "@/i18n/context";
import { useInstitutional } from "@/hooks/use-market-data";
import { type InstitutionalData } from "@/lib/api-client";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { getErrorMessage } from "@/lib/type-guards";
import { GlassPanel, ClippedButton, KpiCard } from "@/components/stratos/primitives";

/** Format a number with thousands separators and +/- sign. */
function formatNet(v: number): string {
  const abs = Math.abs(v).toLocaleString("en-US");
  if (v > 0) return `+${abs}`;
  if (v < 0) return `-${abs}`;
  return "0";
}

/** Color class: TW convention -- red = positive, green = negative. */
function netColor(v: number): string {
  if (v > 0) return "text-[var(--stock-up)]";
  if (v < 0) return "text-[var(--stock-down)]";
  return "text-[var(--text-muted)]";
}

/** Default date range: 30 days ending today. */
function defaultRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - 30);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { start: fmt(start), end: fmt(end) };
}

/** Determine KPI direction from a numeric value. */
function kpiDirection(v: number): "up" | "down" | "flat" {
  if (v > 0) return "up";
  if (v < 0) return "down";
  return "flat";
}

import { AmbientBackground } from "@/components/stratos/ambient";

// ... (helper functions remain the same) ...

export default function InstitutionalPage() {
  const { t } = useI18n();
  const ins = t.institutional;

  const [symbol, setSymbol] = useState("");
  const [query, setQuery] = useState("");
  const [startDate, setStartDate] = useState(defaultRange().start);
  const [endDate, setEndDate] = useState(defaultRange().end);

  const { data, isLoading, error: queryError, refetch } = useInstitutional(
    query,
    startDate,
    endDate,
    !!query,
  );

  const error = queryError ? getErrorMessage(queryError) : null;

  const handleSearch = () => {
    const clean = symbol.trim().replace(".TW", "").replace(".TWO", "");
    if (clean) setQuery(clean);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  const totals = useMemo(() => {
    if (!data || data.length === 0) return null;
    return data.reduce(
      (acc, row) => ({
        foreign: acc.foreign + row.foreign_net,
        trust: acc.trust + row.trust_net,
        dealer: acc.dealer + row.dealer_net,
        total: acc.total + row.total_net,
      }),
      { foreign: 0, trust: 0, dealer: 0, total: 0 },
    );
  }, [data]);

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 border-b border-[var(--border-subtle)] pb-4 gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              {ins.title}
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              {ins.subtitle}
            </p>
          </div>
        </div>

        <GlassPanel title="QUERY BUILDER" className="mb-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="md:col-span-2">
              <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-2">
                SECURITY SYMBOL
              </h4>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={ins.searchPlaceholder}
                  className="flex-1 w-full px-4 py-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm font-bold text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none transition-all"
                />
                <ClippedButton
                  variant="red-solid"
                  size="md"
                  onClick={handleSearch}
                  disabled={!symbol.trim() || isLoading}
                >
                  {isLoading ? "SEARCHING..." : "SEARCH"}
                </ClippedButton>
              </div>
            </div>
            
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-2">
                DATE RANGE
              </h4>
              <div className="flex gap-2">
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="flex-1 w-full px-4 py-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-xs font-bold text-[var(--foreground)]"
                />
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="flex-1 w-full px-4 py-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-xs font-bold text-[var(--foreground)]"
                />
              </div>
            </div>
          </div>
        </GlassPanel>

        {totals && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <KpiCard label="FOREIGN NET" value={formatNet(totals.foreign)} delta="Aggregated" direction={kpiDirection(totals.foreign)} />
            <KpiCard label="TRUST NET" value={formatNet(totals.trust)} delta="Aggregated" direction={kpiDirection(totals.trust)} />
            <KpiCard label="DEALER NET" value={formatNet(totals.dealer)} delta="Aggregated" direction={kpiDirection(totals.dealer)} />
            <KpiCard label="TOTAL NET" value={formatNet(totals.total)} delta="Aggregated" direction={kpiDirection(totals.total)} />
          </div>
        )}

        {isLoading ? (
          <div className="py-20 flex justify-center"><LoadingSpinner /></div>
        ) : error ? (
          <GlassPanel className="py-20 text-center"><p className="text-red-400 font-bold">{error.toUpperCase()}</p></GlassPanel>
        ) : data && data.length > 0 ? (
          <GlassPanel noPadding title="INSTITUTIONAL FLOWS DATASTREAM">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">Date</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Foreign Net</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Trust Net</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Dealer Net</th>
                    <th className="px-4 py-3 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest text-right">Total Net</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {data.map((row) => (
                    <tr key={row.date} className="hover:bg-[var(--card-hover)] transition-colors">
                      <td className="px-4 py-3 text-xs font-bold text-[var(--text-secondary)] tabular-nums">{row.date}</td>
                      <td className={`px-4 py-3 text-sm font-bold tabular-nums text-right ${netColor(row.foreign_net)}`}>{formatNet(row.foreign_net)}</td>
                      <td className={`px-4 py-3 text-sm font-bold tabular-nums text-right ${netColor(row.trust_net)}`}>{formatNet(row.trust_net)}</td>
                      <td className={`px-4 py-3 text-sm font-bold tabular-nums text-right ${netColor(row.dealer_net)}`}>{formatNet(row.dealer_net)}</td>
                      <td className={`px-4 py-3 text-sm font-bold tabular-nums text-right ${netColor(row.total_net)}`}>{formatNet(row.total_net)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassPanel>
        ) : (
          <GlassPanel className="py-24 text-center">
            <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-[0.2em]">Awaiting query</p>
          </GlassPanel>
        )}
      </main>
    </div>
  );
}
