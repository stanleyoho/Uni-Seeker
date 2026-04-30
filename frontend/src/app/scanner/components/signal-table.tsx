"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { type StockSignal, type SignalAction } from "@/hooks/use-scanner";

// ---- Action badge colors ----

const ACTION_STYLES: Record<SignalAction, string> = {
  STRONG_BUY:
    "bg-emerald-500/20 text-emerald-300 border-emerald-500/30 font-bold glow-green",
  BUY: "bg-green-500/15 text-green-400 border-green-500/25",
  HOLD: "bg-slate-500/15 text-slate-400 border-slate-500/25",
  SELL: "bg-red-500/15 text-red-400 border-red-500/25",
  STRONG_SELL:
    "bg-red-600/20 text-red-300 border-red-600/30 font-bold glow-red",
};

const ACTION_LABELS: Record<SignalAction, string> = {
  STRONG_BUY: "Strong Buy",
  BUY: "Buy",
  HOLD: "Hold",
  SELL: "Sell",
  STRONG_SELL: "Strong Sell",
};

const ACTION_LABELS_ZH: Record<SignalAction, string> = {
  STRONG_BUY: "強力買進",
  BUY: "買進",
  HOLD: "持有",
  SELL: "賣出",
  STRONG_SELL: "強力賣出",
};

// ---- Small strategy badge ----

function StrategyBadge({ strategy, action }: { strategy: string; action: SignalAction }) {
  const colorMap: Record<SignalAction, string> = {
    STRONG_BUY: "text-emerald-300 bg-emerald-500/10",
    BUY: "text-green-400 bg-green-500/10",
    HOLD: "text-slate-400 bg-slate-500/10",
    SELL: "text-red-400 bg-red-500/10",
    STRONG_SELL: "text-red-300 bg-red-600/10",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${colorMap[action]}`}
    >
      <span className="text-[var(--text-muted)]">{strategy}:</span>
      <span>{ACTION_LABELS_ZH[action]}</span>
    </span>
  );
}

// ---- Centered score bar (-1 to +1) ----

function SignalScoreBar({ score }: { score: number }) {
  // score ranges from -1 to +1, center at 0
  const pct = Math.abs(score) * 50; // max 50% from center
  const isPositive = score >= 0;

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-[var(--bg-secondary)] rounded-full overflow-hidden relative">
        {/* Center line */}
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-[var(--border-color)]" />
        {/* Fill bar */}
        {isPositive ? (
          <div
            className="absolute top-0 bottom-0 rounded-r-full bg-emerald-500 transition-all duration-700 ease-out"
            style={{
              left: "50%",
              width: `${pct}%`,
              boxShadow: "0 0 6px rgba(34, 197, 94, 0.4)",
            }}
          />
        ) : (
          <div
            className="absolute top-0 bottom-0 rounded-l-full bg-red-500 transition-all duration-700 ease-out"
            style={{
              right: "50%",
              width: `${pct}%`,
              boxShadow: "0 0 6px rgba(239, 68, 68, 0.4)",
            }}
          />
        )}
      </div>
      <span
        className={`mono-nums text-xs w-12 text-right ${
          isPositive ? "text-emerald-400" : score < 0 ? "text-red-400" : "text-slate-400"
        }`}
      >
        {score >= 0 ? "+" : ""}
        {score.toFixed(2)}
      </span>
    </div>
  );
}

// ---- Expand row detail ----

function SignalDetailRow({ stock }: { stock: StockSignal }) {
  return (
    <div className="px-4 py-3 bg-[var(--bg-secondary)]/50 border-t border-[var(--border-subtle)] animate-fade-in">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {stock.signals.map((sig) => (
          <div
            key={sig.strategy}
            className="flex flex-col gap-1 px-3 py-2 rounded-lg bg-[var(--card-bg)] border border-[var(--border-subtle)]"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[var(--foreground)]">{sig.strategy}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded border ${ACTION_STYLES[sig.action]}`}
              >
                {ACTION_LABELS_ZH[sig.action]}
              </span>
            </div>
            <p className="text-[10px] text-[var(--text-muted)] leading-relaxed">
              {sig.reason}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- Filter checkboxes ----

const ALL_ACTIONS: SignalAction[] = ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"];

// ---- Sort keys ----

type SortKey = "score" | "symbol" | "name";

// ---- Main component ----

interface SignalTableProps {
  stocks: StockSignal[];
  actionFilter: SignalAction[];
  onActionFilterChange: (actions: SignalAction[]) => void;
}

export function SignalTable({ stocks, actionFilter, onActionFilterChange }: SignalTableProps) {
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "score" ? "desc" : "asc");
    }
  };

  const toggleAction = (action: SignalAction) => {
    if (actionFilter.includes(action)) {
      onActionFilterChange(actionFilter.filter((a) => a !== action));
    } else {
      onActionFilterChange([...actionFilter, action]);
    }
  };

  const filteredAndSorted = useMemo(() => {
    let filtered = stocks;
    if (actionFilter.length > 0 && actionFilter.length < ALL_ACTIONS.length) {
      filtered = stocks.filter((s) => actionFilter.includes(s.compositeAction));
    }

    const sorted = [...filtered].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "score") cmp = a.score - b.score;
      else if (sortKey === "symbol") cmp = a.symbol.localeCompare(b.symbol);
      else cmp = a.name.localeCompare(b.name);
      return sortDir === "desc" ? -cmp : cmp;
    });

    return sorted;
  }, [stocks, actionFilter, sortKey, sortDir]);

  const SortIcon = ({ active, dir }: { active: boolean; dir: "asc" | "desc" }) =>
    active ? (
      <svg className="w-3 h-3 ml-0.5 inline-block" fill="currentColor" viewBox="0 0 12 12">
        {dir === "asc" ? <path d="M6 3l4 5H2z" /> : <path d="M6 9l4-5H2z" />}
      </svg>
    ) : null;

  return (
    <div>
      {/* Action filter */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <span className="text-xs text-[var(--text-muted)]">篩選訊號:</span>
        {ALL_ACTIONS.map((action) => {
          const isActive = actionFilter.includes(action);
          return (
            <button
              key={action}
              onClick={() => toggleAction(action)}
              className={`text-[10px] px-2 py-1 rounded-md border transition-all duration-150 ${
                isActive
                  ? ACTION_STYLES[action]
                  : "text-[var(--text-muted)] bg-transparent border-[var(--border-color)] opacity-50 hover:opacity-80"
              }`}
              aria-pressed={isActive}
              aria-label={`Filter ${ACTION_LABELS[action]}`}
            >
              {ACTION_LABELS_ZH[action]}
            </button>
          );
        })}
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-2">
        {filteredAndSorted.length === 0 && (
          <p className="text-center text-[var(--text-muted)] py-8 text-sm">
            無符合條件的訊號
          </p>
        )}
        {filteredAndSorted.map((stock) => (
          <div key={stock.symbol}>
            <button
              onClick={() =>
                setExpandedSymbol((s) => (s === stock.symbol ? null : stock.symbol))
              }
              className="w-full text-left bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-3 hover:bg-[var(--card-hover)] transition-colors duration-150"
              aria-expanded={expandedSymbol === stock.symbol}
            >
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-[var(--foreground)] font-semibold text-sm">{stock.symbol}</span>
                  <span className="text-[var(--text-muted)] text-[10px] ml-1.5">
                    {stock.name}
                  </span>
                </div>
                <span
                  className={`text-[10px] px-2 py-1 rounded-md border ${ACTION_STYLES[stock.compositeAction]}`}
                >
                  {ACTION_LABELS_ZH[stock.compositeAction]}
                </span>
              </div>
              <div className="mb-2">
                <SignalScoreBar score={stock.score} />
              </div>
              <div className="flex flex-wrap gap-1">
                {stock.signals.map((sig) => (
                  <StrategyBadge
                    key={sig.strategy}
                    strategy={sig.strategy}
                    action={sig.action}
                  />
                ))}
              </div>
            </button>
            {expandedSymbol === stock.symbol && <SignalDetailRow stock={stock} />}
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm" role="grid">
          <thead>
            <tr className="border-b border-[var(--border-color)] text-[var(--text-muted)] text-xs uppercase tracking-wider">
              <th
                className="px-3 py-2 text-left cursor-pointer select-none hover:text-[var(--foreground)] transition-colors"
                onClick={() => handleSort("symbol")}
              >
                <span className="inline-flex items-center">
                  代號
                  <SortIcon active={sortKey === "symbol"} dir={sortDir} />
                </span>
              </th>
              <th
                className="px-3 py-2 text-left cursor-pointer select-none hover:text-[var(--foreground)] transition-colors"
                onClick={() => handleSort("name")}
              >
                <span className="inline-flex items-center">
                  名稱
                  <SortIcon active={sortKey === "name"} dir={sortDir} />
                </span>
              </th>
              <th className="px-3 py-2 text-center">綜合訊號</th>
              <th
                className="px-3 py-2 text-left w-48 cursor-pointer select-none hover:text-[var(--foreground)] transition-colors"
                onClick={() => handleSort("score")}
              >
                <span className="inline-flex items-center">
                  分數
                  <SortIcon active={sortKey === "score"} dir={sortDir} />
                </span>
              </th>
              <th className="px-3 py-2 text-left">個別訊號</th>
              <th className="px-3 py-2 text-center w-20">操作</th>
            </tr>
          </thead>
          <tbody>
            {filteredAndSorted.length === 0 && (
              <tr>
                <td colSpan={6} className="text-center py-12 text-[var(--text-muted)]">
                  無符合條件的訊號
                </td>
              </tr>
            )}
            {filteredAndSorted.map((stock, idx) => (
              <tr key={stock.symbol} className="group">
                {/* Main row */}
                <td
                  colSpan={6}
                  className="p-0"
                >
                  <button
                    onClick={() =>
                      setExpandedSymbol((s) =>
                        s === stock.symbol ? null : stock.symbol
                      )
                    }
                    className={`w-full text-left grid grid-cols-[minmax(80px,1fr)_minmax(80px,1fr)_120px_200px_1fr_80px] items-center border-b border-[var(--border-subtle)] hover:bg-[var(--card-active)]/40 transition-colors duration-150 ${
                      idx % 2 === 1 ? "bg-[var(--background)]/30" : ""
                    }`}
                    aria-expanded={expandedSymbol === stock.symbol}
                  >
                    <span className="px-3 py-2">
                      <Link
                        href={`/stocks/${encodeURIComponent(stock.symbol)}`}
                        className="text-[var(--foreground)] font-semibold text-xs hover:text-[var(--accent-blue)] transition-colors duration-150"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {stock.symbol}
                      </Link>
                    </span>
                    <span className="px-3 py-2 text-[var(--text-secondary)] text-xs truncate">
                      {stock.name}
                    </span>
                    <span className="px-3 py-2 text-center">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 text-[10px] rounded-md border ${ACTION_STYLES[stock.compositeAction]}`}
                      >
                        {ACTION_LABELS_ZH[stock.compositeAction]}
                      </span>
                    </span>
                    <span className="px-3 py-2">
                      <SignalScoreBar score={stock.score} />
                    </span>
                    <span className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {stock.signals.map((sig) => (
                          <StrategyBadge
                            key={sig.strategy}
                            strategy={sig.strategy}
                            action={sig.action}
                          />
                        ))}
                      </div>
                    </span>
                    <span className="px-3 py-2 text-center">
                      <Link
                        href={`/backtest?symbol=${encodeURIComponent(stock.symbol)}`}
                        className="text-[10px] text-[var(--accent-blue)] hover:text-blue-300 transition-colors font-medium"
                        onClick={(e) => e.stopPropagation()}
                      >
                        回測
                      </Link>
                    </span>
                  </button>
                  {/* Expanded detail */}
                  {expandedSymbol === stock.symbol && (
                    <SignalDetailRow stock={stock} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
