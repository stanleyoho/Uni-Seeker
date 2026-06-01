"use client";

import { type StockSignal, type SignalAction } from "@/hooks/use-scanner";
import { QuoteRow } from "@/components/quote-row";
import { classifySentiment } from "@/lib/sentiment";

const ACTION_CONFIG: Record<SignalAction, { label: string; color: string; bg: string }> = {
  STRONG_BUY: { label: "STRONG BUY", color: "var(--stock-down)", bg: "rgba(0,200,83,0.1)" },
  BUY: { label: "BUY", color: "#22c55e", bg: "rgba(34,197,94,0.08)" },
  HOLD: { label: "HOLD", color: "#64748b", bg: "rgba(100,116,139,0.08)" },
  SELL: { label: "SELL", color: "#f87171", bg: "rgba(248,113,113,0.08)" },
  STRONG_SELL: { label: "STRONG SELL", color: "var(--stock-up)", bg: "rgba(238,63,44,0.1)" },
};

interface SignalTableProps {
  stocks: StockSignal[];
  actionFilter: SignalAction[];
  onActionFilterChange: (actions: SignalAction[]) => void;
}

export function SignalTable({ stocks, actionFilter, onActionFilterChange }: SignalTableProps) {
  const filtered = stocks.filter((s) => actionFilter.includes(s.compositeAction));

  const toggleFilter = (action: SignalAction) => {
    if (actionFilter.includes(action)) {
      onActionFilterChange(actionFilter.filter((a) => a !== action));
    } else {
      onActionFilterChange([...actionFilter, action]);
    }
  };

  return (
    <div>
      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 mb-4">
        {(Object.keys(ACTION_CONFIG) as SignalAction[]).map((action) => {
          const cfg = ACTION_CONFIG[action];
          const active = actionFilter.includes(action);
          return (
            <button
              key={action}
              onClick={() => toggleFilter(action)}
              className="px-3 py-1 text-[10px] font-bold uppercase tracking-wider transition-all border"
              style={{
                color: active ? cfg.color : "var(--text-muted)",
                background: active ? cfg.bg : "transparent",
                borderColor: active ? cfg.color : "var(--border-subtle)",
                opacity: active ? 1 : 0.5,
              }}
            >
              {cfg.label}
            </button>
          );
        })}
      </div>

      {/*
        Scanner results table. The Quote column used to show symbol-only
        (`stock.symbol.replace('.TW', '')`) with the name in a separate
        column. The user asked every stock-listing surface to show
        symbol + name + price + abs change + percent. StockSignalResponse
        ships symbol/name/composite_action/score but no price/change —
        QuoteRow renders an em-dash for the missing fields so the
        backend gap is visible to ops without breaking the column.
      */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)]">
              <th className="text-left py-2 px-3 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">Quote</th>
              <th className="text-center py-2 px-3 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">Signal</th>
              <th className="text-right py-2 px-3 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">Score</th>
              <th className="text-left py-2 px-3 text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">Strategies</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((stock) => {
              const cfg = ACTION_CONFIG[stock.compositeAction];
              // Score is a composite signal intensity (not a percent),
              // but the 5-level taxonomy maps cleanly: |score|>=1 is
              // a "heated" / "deep" conviction, the flat band absorbs
              // near-zero noise. Sharing the helper keeps the visual
              // vocabulary identical across heatmap, scanner, low-base.
              const scoreSentiment = classifySentiment(stock.score);
              return (
                <tr key={stock.symbol} className="border-b border-[var(--border-subtle)] hover:bg-[var(--card-hover)] transition-colors">
                  <td className="py-1.5 px-3 min-w-[200px]">
                    <QuoteRow
                      symbol={stock.symbol}
                      name={stock.name}
                      href={`/stocks/${encodeURIComponent(stock.symbol)}`}
                      className="!border-b-0"
                    />
                  </td>
                  <td className="py-2.5 px-3 text-center">
                    <span
                      className="inline-block px-2 py-0.5 text-[10px] font-bold"
                      style={{ color: cfg.color, background: cfg.bg }}
                    >
                      {cfg.label}
                    </span>
                  </td>
                  <td className={`py-2.5 px-3 text-right font-mono text-xs font-bold tabular-nums ${scoreSentiment.colorClass}`}>
                    <span aria-hidden="true" className="mr-1">{scoreSentiment.emoji}</span>
                    {scoreSentiment.arrow} {stock.score > 0 ? "+" : ""}{stock.score.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3">
                    <div className="flex flex-wrap gap-1">
                      {stock.signals.map((sig, i) => (
                        <span key={i} className="text-[9px] font-bold px-1.5 py-0.5 bg-[var(--bg-secondary)] text-[var(--text-muted)]">
                          {sig.strategy}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="py-12 text-center text-xs text-[var(--text-muted)] uppercase font-bold tracking-widest">
            No results matching filter
          </div>
        )}
      </div>
    </div>
  );
}
