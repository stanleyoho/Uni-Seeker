"use client";

import { useState, useMemo } from "react";
import { useI18n } from "@/i18n/context";
import { useInstitutional } from "@/hooks/use-market-data";
import { type InstitutionalData } from "@/lib/api-client";
import { LoadingSpinner } from "@/components/ui/loading";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { DataTable, type Column } from "@/components/ui/data-table";
import { getErrorMessage } from "@/lib/type-guards";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";

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

  // ----- Table columns -----
  const columns: Column<InstitutionalData>[] = useMemo(
    () => [
      {
        key: "date",
        header: ins.date,
        width: "w-24",
        render: (row) => (
          <span className="text-[var(--text-secondary)] mono-nums text-xs">{row.date}</span>
        ),
      },
      {
        key: "foreign_net",
        header: `${ins.foreign} ${ins.netBuy}`,
        align: "right" as const,
        render: (row) => (
          <span className={`mono-nums text-xs font-medium ${netColor(row.foreign_net)}`}>
            {formatNet(row.foreign_net)}
          </span>
        ),
      },
      {
        key: "trust_net",
        header: `${ins.trust} ${ins.netBuy}`,
        align: "right" as const,
        render: (row) => (
          <span className={`mono-nums text-xs font-medium ${netColor(row.trust_net)}`}>
            {formatNet(row.trust_net)}
          </span>
        ),
      },
      {
        key: "dealer_net",
        header: `${ins.dealer} ${ins.netBuy}`,
        align: "right" as const,
        render: (row) => (
          <span className={`mono-nums text-xs font-medium ${netColor(row.dealer_net)}`}>
            {formatNet(row.dealer_net)}
          </span>
        ),
      },
      {
        key: "total_net",
        header: ins.total,
        align: "right" as const,
        render: (row) => (
          <span className={`mono-nums text-xs font-bold ${netColor(row.total_net)}`}>
            {formatNet(row.total_net)}
          </span>
        ),
      },
    ],
    [ins],
  );

  const inputStyle: React.CSSProperties = {
    background: "var(--glass-bg)",
    border: "1px solid var(--border-color)",
    color: "var(--foreground)",
    outline: "none",
  };

  return (
    <div className="max-w-[1440px] mx-auto px-4 md:px-6 py-4 animate-fade-in">
      {/* Header */}
      <div className="mb-4">
        <h1
          style={{
            fontSize: 18,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "-0.04em",
            color: "var(--foreground)",
          }}
        >
          {ins.title}
        </h1>
        <p className="text-[var(--text-muted)] text-xs mt-0.5">{ins.subtitle}</p>
      </div>

      {/* Search bar + date range */}
      <GlassPanel className="mb-4">
        <div className="flex flex-col md:flex-row gap-3">
          <div className="flex flex-1 gap-2">
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={ins.searchPlaceholder}
              className="flex-1 px-3 py-2 text-sm rounded-lg placeholder:text-[var(--text-muted)] focus:border-[var(--accent-cyan)] transition-colors duration-200"
              style={inputStyle}
            />
            <ClippedButton
              variant="red-solid"
              size="md"
              onClick={handleSearch}
              disabled={!symbol.trim() || isLoading}
            >
              {isLoading ? ins.loading : t.search.button}
            </ClippedButton>
          </div>
          <div className="flex gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-2 py-2 text-xs rounded-lg focus:border-[var(--accent-cyan)] transition-colors duration-200"
              style={inputStyle}
            />
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-2 py-2 text-xs rounded-lg focus:border-[var(--accent-cyan)] transition-colors duration-200"
              style={inputStyle}
            />
          </div>
        </div>
      </GlassPanel>

      {/* Loading */}
      {isLoading && <LoadingSpinner text={ins.loading} size="sm" />}

      {/* Error */}
      {error && !isLoading && <ErrorState message={error} onRetry={() => refetch()} />}

      {/* Empty state when no query yet */}
      {!query && !isLoading && (
        <GlassPanel>
          <EmptyState message={ins.searchPlaceholder} />
        </GlassPanel>
      )}

      {/* Empty result */}
      {query && data && data.length === 0 && !isLoading && (
        <GlassPanel>
          <EmptyState message={ins.noData} />
        </GlassPanel>
      )}

      {/* Mobile cards */}
      {data && data.length > 0 && (
        <div className="md:hidden space-y-2">
          {data.map((row) => (
            <GlassPanel key={row.date}>
              <div className="text-[var(--text-secondary)] text-xs mono-nums mb-2">{row.date}</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                <span className="text-[var(--text-muted)]">{ins.foreign}</span>
                <span className={`mono-nums text-right font-medium ${netColor(row.foreign_net)}`}>
                  {formatNet(row.foreign_net)}
                </span>
                <span className="text-[var(--text-muted)]">{ins.trust}</span>
                <span className={`mono-nums text-right font-medium ${netColor(row.trust_net)}`}>
                  {formatNet(row.trust_net)}
                </span>
                <span className="text-[var(--text-muted)]">{ins.dealer}</span>
                <span className={`mono-nums text-right font-medium ${netColor(row.dealer_net)}`}>
                  {formatNet(row.dealer_net)}
                </span>
                <span className="text-[var(--text-muted)] font-semibold">{ins.total}</span>
                <span className={`mono-nums text-right font-bold ${netColor(row.total_net)}`}>
                  {formatNet(row.total_net)}
                </span>
              </div>
            </GlassPanel>
          ))}
        </div>
      )}

      {/* Desktop table */}
      {data && data.length > 0 && (
        <GlassPanel className="hidden md:block" noPadding>
          <DataTable columns={columns} data={data} rowKey={(row) => row.date} compact />
        </GlassPanel>
      )}
    </div>
  );
}
