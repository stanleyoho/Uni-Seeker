"use client";

import { useState } from "react";
import Link from "next/link";
import {
  GlassPanel,
  ClippedButton,
} from "@/components/stratos/primitives";
import { AmbientBackground } from "@/components/stratos/ambient";
import { LoadingSpinner } from "@/components/ui/loading";
import { useBacktestHistory, useBacktestResult } from "@/hooks/use-backtest";
import type { BacktestHistoryItem } from "@/lib/api-client";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

/* ------------------------------------------------------------------ */
/*  Sortable table header                                               */
/* ------------------------------------------------------------------ */

function SortTh({
  field,
  label,
  align = "right",
  sortField,
  sortDir,
  onSort,
}: {
  field: keyof BacktestHistoryItem;
  label: string;
  align?: "left" | "right";
  sortField: keyof BacktestHistoryItem;
  sortDir: "asc" | "desc";
  onSort: (field: keyof BacktestHistoryItem) => void;
}) {
  return (
    <th
      className={`py-3 px-4 text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)] cursor-pointer hover:text-[var(--foreground)] transition-colors select-none ${align === "right" ? "text-right" : "text-left"}`}
      onClick={() => onSort(field)}
    >
      {label}
      {sortField === field && (
        <span className="ml-1 text-[var(--accent-cyan)]">
          {sortDir === "asc" ? "↑" : "↓"}
        </span>
      )}
    </th>
  );
}

/* ------------------------------------------------------------------ */
/*  Return badge                                                        */
/* ------------------------------------------------------------------ */

function ReturnBadge({ value }: { value: number }) {
  const pos = value >= 0;
  return (
    <span
      className={`tabular-nums font-bold text-xs ${pos ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}
    >
      {pos ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Detail Modal                                                        */
/* ------------------------------------------------------------------ */

function DetailPanel({
  id,
  onClose,
}: {
  id: number;
  onClose: () => void;
}) {
  const { data, isLoading } = useBacktestResult(id);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-10 px-4 pb-10">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="relative w-full max-w-4xl max-h-[85vh] overflow-y-auto"
        style={{
          background: "var(--glass-bg)",
          backdropFilter: "var(--glass-blur)",
          border: "1px solid var(--border-color)",
          boxShadow: "var(--glass-shadow)",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)]">
          <div>
            <h2 className="text-lg font-bold text-[var(--foreground)] uppercase tracking-tight">
              BACKTEST RESULT #{id}
            </h2>
            {data && (
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest mt-0.5">
                {data.symbol} — {data.strategy_name}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 text-[var(--text-muted)] hover:text-[var(--foreground)] border border-[var(--border-subtle)] transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <LoadingSpinner />
            </div>
          ) : data ? (
            <DetailContent item={data} />
          ) : (
            <p className="text-center text-[var(--text-muted)] py-20 uppercase font-bold text-sm">
              RESULT NOT FOUND
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Detail Content                                                      */
/* ------------------------------------------------------------------ */

function DetailContent({ item }: { item: BacktestHistoryItem }) {
  const chartData = (item.equity_curve || []).map((val, i) => ({
    day: i,
    equity: Math.round(val),
  }));

  const metrics = [
    { label: "TOTAL RETURN", value: `${item.total_return >= 0 ? "+" : ""}${item.total_return.toFixed(2)}%`, color: item.total_return >= 0 ? "var(--stock-up)" : "var(--stock-down)" },
    { label: "ANNUALIZED", value: `${item.annualized_return >= 0 ? "+" : ""}${item.annualized_return.toFixed(2)}%`, color: item.annualized_return >= 0 ? "var(--stock-up)" : "var(--stock-down)" },
    { label: "MAX DRAWDOWN", value: `${item.max_drawdown.toFixed(2)}%`, color: "var(--stock-down)" },
    { label: "SHARPE RATIO", value: item.sharpe_ratio.toFixed(2), color: item.sharpe_ratio >= 1 ? "var(--stock-up)" : "var(--foreground)" },
    { label: "WIN RATE", value: `${item.win_rate.toFixed(1)}%`, color: item.win_rate >= 50 ? "var(--stock-up)" : "var(--foreground)" },
    { label: "PROFIT FACTOR", value: item.profit_factor.toFixed(2), color: item.profit_factor >= 1 ? "var(--stock-up)" : "var(--stock-down)" },
    { label: "TOTAL TRADES", value: item.total_trades.toString(), color: "var(--foreground)" },
    { label: "TRADING DAYS", value: item.trading_days?.toString() ?? "-", color: "var(--foreground)" },
  ];

  return (
    <>
      {/* Meta */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "SYMBOL", value: item.symbol },
          { label: "STRATEGY", value: item.strategy_name },
          { label: "TYPE", value: item.backtest_type.toUpperCase() },
          { label: "DATE", value: new Date(item.created_at).toLocaleDateString() },
        ].map((m) => (
          <div key={m.label} className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-3">
            <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest">{m.label}</p>
            <p className="text-sm font-bold text-[var(--foreground)] mt-1 truncate uppercase">{m.value}</p>
          </div>
        ))}
      </div>

      {/* Params */}
      {item.strategy_params && Object.keys(item.strategy_params).length > 0 && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] px-4 py-3">
          <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2">STRATEGY PARAMS</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(item.strategy_params).map(([k, v]) => (
              <span key={k} className="text-[10px] font-bold px-2 py-0.5 bg-[var(--card-hover)] border border-[var(--border-subtle)] text-[var(--foreground)]">
                {k}={String(v)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {metrics.map((m) => (
          <div key={m.label} className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-3">
            <p className="text-[9px] font-bold text-[var(--text-muted)] uppercase tracking-widest">{m.label}</p>
            <p className="text-xl font-bold tabular-nums mt-1" style={{ color: m.color }}>{m.value}</p>
          </div>
        ))}
      </div>

      {/* Buy & Hold comparison */}
      {item.buy_hold_return !== null && (
        <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] px-5 py-4 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">BUY & HOLD BENCHMARK</p>
            <p className="text-lg font-bold tabular-nums mt-1" style={{ color: (item.buy_hold_return ?? 0) >= 0 ? "var(--stock-up)" : "var(--stock-down)" }}>
              {(item.buy_hold_return ?? 0) >= 0 ? "+" : ""}{(item.buy_hold_return ?? 0).toFixed(2)}%
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">ALPHA</p>
            {(() => {
              const alpha = item.total_return - (item.buy_hold_return ?? 0);
              return (
                <p className="text-lg font-bold tabular-nums mt-1" style={{ color: alpha >= 0 ? "var(--stock-up)" : "var(--stock-down)" }}>
                  {alpha >= 0 ? "+" : ""}{alpha.toFixed(2)}%
                </p>
              );
            })()}
          </div>
        </div>
      )}

      {/* Equity curve */}
      {chartData.length > 0 && (
        <div>
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)] mb-3">EQUITY CURVE</h4>
          <div className="h-[280px] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-4">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <defs>
                  <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-cyan)" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="var(--accent-cyan)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="3 3" />
                <XAxis dataKey="day" stroke="var(--text-muted)" tick={{ fontSize: 9 }} />
                <YAxis stroke="var(--text-muted)" tick={{ fontSize: 9 }} domain={["dataMin", "dataMax"]}
                  tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}K`} />
                <Tooltip
                  contentStyle={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)", fontSize: 11 }}
                  labelStyle={{ color: "var(--foreground)", fontWeight: "bold" }}
                  formatter={(v: unknown) => [`$${Number(v).toLocaleString()}`, "Equity"]}
                />
                <Area type="monotone" dataKey="equity" stroke="var(--accent-cyan)" strokeWidth={2}
                  fillOpacity={1} fill="url(#eqGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Trade log */}
      {item.trade_log && item.trade_log.length > 0 && (
        <div>
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)] mb-3">
            TRADE LOG ({item.trade_log.length} EXECUTIONS)
          </h4>
          <div className="overflow-x-auto max-h-[240px] overflow-y-auto border border-[var(--border-subtle)]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[var(--bg-secondary)]">
                <tr className="border-b border-[var(--border-subtle)]">
                  {["DATE", "ACTION", "PRICE", "SHARES", "REASON"].map((h) => (
                    <th key={h} className={`py-2 px-3 text-[9px] font-bold uppercase text-[var(--text-muted)] ${h === "PRICE" || h === "SHARES" ? "text-right" : "text-left"}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {item.trade_log.map((t, i) => (
                  <tr key={i} className="border-b border-[var(--border-subtle)] hover:bg-[var(--card-hover)]">
                    <td className="py-1.5 px-3 font-mono">{t.date}</td>
                    <td className="py-1.5 px-3">
                      <span className={`font-bold ${t.action === "BUY" ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}>
                        {t.action}
                      </span>
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono tabular-nums">{Number(t.price).toFixed(2)}</td>
                    <td className="py-1.5 px-3 text-right font-mono tabular-nums">{t.shares}</td>
                    <td className="py-1.5 px-3 text-[var(--text-muted)] truncate max-w-[160px]">{t.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  History row                                                         */
/* ------------------------------------------------------------------ */

function HistoryRow({
  item,
  onSelect,
}: {
  item: BacktestHistoryItem;
  onSelect: (id: number) => void;
}) {
  const params = Object.entries(item.strategy_params || {});
  const paramStr = params.length > 0
    ? `(${params.map(([k, v]) => `${k}=${v}`).join(", ")})`
    : "";

  return (
    <tr
      className="border-b border-[var(--border-subtle)] hover:bg-[var(--card-hover)] cursor-pointer transition-colors"
      onClick={() => onSelect(item.id)}
    >
      <td className="py-3 px-4 font-mono text-xs tabular-nums text-[var(--text-muted)]">
        #{item.id}
      </td>
      <td className="py-3 px-4">
        <span className="text-xs font-bold text-[var(--foreground)] uppercase">{item.symbol}</span>
      </td>
      <td className="py-3 px-4">
        <div>
          <span className="text-xs font-bold text-[var(--foreground)] uppercase">{item.strategy_name}</span>
          {paramStr && (
            <span className="text-[10px] text-[var(--text-muted)] ml-1">{paramStr}</span>
          )}
        </div>
        <span className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider">{item.backtest_type}</span>
      </td>
      <td className="py-3 px-4 text-right">
        <ReturnBadge value={item.total_return} />
      </td>
      <td className="py-3 px-4 text-right font-mono text-xs tabular-nums text-[var(--foreground)]">
        {item.sharpe_ratio.toFixed(2)}
      </td>
      <td className="py-3 px-4 text-right font-mono text-xs tabular-nums text-[var(--stock-down)]">
        {item.max_drawdown.toFixed(2)}%
      </td>
      <td className="py-3 px-4 text-right font-mono text-xs tabular-nums text-[var(--foreground)]">
        {item.win_rate.toFixed(1)}%
      </td>
      <td className="py-3 px-4 text-right font-mono text-xs text-[var(--text-muted)]">
        {item.total_trades}
      </td>
      <td className="py-3 px-4 text-right text-[10px] text-[var(--text-muted)]">
        {new Date(item.created_at).toLocaleDateString()}
      </td>
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                           */
/* ------------------------------------------------------------------ */

export default function BacktestHistoryPage() {
  const [symbolFilter, setSymbolFilter] = useState("");
  const [appliedFilter, setAppliedFilter] = useState<string | undefined>(undefined);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [sortField, setSortField] = useState<keyof BacktestHistoryItem>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const { data, isLoading } = useBacktestHistory(appliedFilter, 100);
  const items = data?.results ?? [];

  const sorted = [...items].sort((a, b) => {
    const av = a[sortField] as number | string;
    const bv = b[sortField] as number | string;
    if (typeof av === "number" && typeof bv === "number") {
      return sortDir === "asc" ? av - bv : bv - av;
    }
    return sortDir === "asc"
      ? String(av).localeCompare(String(bv))
      : String(bv).localeCompare(String(av));
  });

  const handleSort = (field: keyof BacktestHistoryItem) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in space-y-6">

        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              Backtest History
            </h1>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest mt-1">
              {data?.total ?? 0} SAVED RESULTS
            </p>
          </div>
          <Link href="/portfolio/backtest">
            <ClippedButton variant="red-solid" size="sm">
              ← NEW BACKTEST
            </ClippedButton>
          </Link>
        </div>

        {/* Filter */}
        <GlassPanel>
          <div className="flex gap-3 items-center">
            <input
              type="text"
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === "Enter") setAppliedFilter(symbolFilter || undefined);
              }}
              placeholder="FILTER BY SYMBOL (e.g., 2330.TW)"
              className="flex-1 px-4 py-2.5 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm font-bold text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none transition-all"
            />
            <ClippedButton
              variant="cyan-ghost"
              size="sm"
              onClick={() => setAppliedFilter(symbolFilter || undefined)}
            >
              FILTER
            </ClippedButton>
            {appliedFilter && (
              <ClippedButton
                variant="red-ghost"
                size="sm"
                onClick={() => {
                  setSymbolFilter("");
                  setAppliedFilter(undefined);
                }}
              >
                CLEAR
              </ClippedButton>
            )}
          </div>
        </GlassPanel>

        {/* Table */}
        <GlassPanel noPadding>
          {isLoading ? (
            <div className="flex items-center justify-center py-24">
              <LoadingSpinner />
            </div>
          ) : sorted.length === 0 ? (
            <div className="py-24 text-center">
              <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-[0.2em]">
                NO BACKTEST RESULTS
              </p>
              <p className="text-[10px] text-[var(--text-muted)] mt-2 uppercase">
                RUN YOUR FIRST BACKTEST TO SEE RESULTS HERE
              </p>
              <div className="mt-6">
                <Link href="/portfolio/backtest">
                  <ClippedButton variant="red-solid" size="sm">
                    LAUNCH BACKTEST
                  </ClippedButton>
                </Link>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-[var(--border-subtle)]">
                  <tr>
                    <th className="py-3 px-4 text-left text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)]">ID</th>
                    <SortTh field="symbol" label="SYMBOL" align="left" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <th className="py-3 px-4 text-left text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)]">STRATEGY</th>
                    <SortTh field="total_return" label="RETURN" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <SortTh field="sharpe_ratio" label="SHARPE" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <SortTh field="max_drawdown" label="DRAWDOWN" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <SortTh field="win_rate" label="WIN %" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <SortTh field="total_trades" label="TRADES" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                    <SortTh field="created_at" label="DATE" sortField={sortField} sortDir={sortDir} onSort={handleSort} />
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((item) => (
                    <HistoryRow key={item.id} item={item} onSelect={setSelectedId} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </GlassPanel>
      </main>

      {/* Detail Modal */}
      {selectedId !== null && (
        <DetailPanel id={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}
