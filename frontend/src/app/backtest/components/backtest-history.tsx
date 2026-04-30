"use client";

import { useState, useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { useBacktestHistory } from "@/hooks/use-backtest";
import { downloadCSV } from "@/lib/csv-export";
import type { BacktestHistoryItem, TradeLogEntry } from "@/lib/api-client";

/* ══════════════════════════════════════════════════════════════════
   Helpers
   ══════════════════════════════════════════════════════════════════ */

function fmtPct(v: number): string {
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}

function fmtNum(v: number, d = 2): string {
  return v.toFixed(d);
}

type SortKey = "total_return" | "win_rate" | "sharpe_ratio" | "total_trades";

/* ── Strategy Signal Parser ── */

interface SignalRule {
  indicator: string;
  buy: string;
  sell: string;
}

function parseStrategySignals(params: Record<string, unknown>): { mode: string; rules: SignalRule[] } {
  const rules: SignalRule[] = [];
  const mode = (params.mode as string) || "";

  // RSI
  if (params.rsi_period || params.rsi_buy || params.rsi_sell) {
    const period = params.rsi_period ?? 14;
    const buy = params.rsi_buy ?? 30;
    const sell = params.rsi_sell ?? 70;
    rules.push({
      indicator: `RSI (${period}日)`,
      buy: `RSI 跌破 ${buy} 進場（超賣反彈）`,
      sell: `RSI 突破 ${sell} 出場（超買回落）`,
    });
  }

  // BIAS
  if (params.bias_period || params.bias_buy || params.bias_sell) {
    const period = params.bias_period ?? 20;
    const buy = params.bias_buy ?? -5;
    const sell = params.bias_sell ?? 5;
    rules.push({
      indicator: `乖離率 (${period}日)`,
      buy: `乖離率 ≤ ${buy}% 進場（股價偏離均線過低）`,
      sell: `乖離率 ≥ ${sell}% 出場（股價偏離均線過高）`,
    });
  }

  // Bollinger Bands
  if (params.bb_period || params.bb_std) {
    const period = params.bb_period ?? 20;
    const std = params.bb_std ?? 2.0;
    rules.push({
      indicator: `布林通道 (${period}日, ${std}σ)`,
      buy: `股價跌破布林下軌進場（極端超賣）`,
      sell: `股價突破布林上軌出場（極端超買）`,
    });
  }

  // MACD
  if (params.macd_fast || params.macd_slow) {
    const fast = params.macd_fast ?? 12;
    const slow = params.macd_slow ?? 26;
    rules.push({
      indicator: `MACD (${fast}, ${slow})`,
      buy: `MACD 線上穿信號線進場（多方動能轉強）`,
      sell: `MACD 線下穿信號線出場（空方動能轉強）`,
    });
  }

  // KD
  if (params.kd_period || params.kd_buy || params.kd_sell) {
    const period = params.kd_period ?? 9;
    const buy = params.kd_buy ?? 20;
    const sell = params.kd_sell ?? 80;
    rules.push({
      indicator: `KD (${period}日)`,
      buy: `K 值跌破 ${buy} 進場（超賣區）`,
      sell: `K 值突破 ${sell} 出場（超買區）`,
    });
  }

  // MA Crossover
  if (params.ma_short || params.ma_long) {
    const short = params.ma_short ?? 5;
    const long = params.ma_long ?? 20;
    rules.push({
      indicator: `均線交叉 (${short}日/${long}日)`,
      buy: `短均線上穿長均線進場（黃金交叉）`,
      sell: `短均線下穿長均線出場（死亡交叉）`,
    });
  }

  return { mode, rules };
}

function getModeLabel(mode: string): string {
  switch (mode) {
    case "all": return "全部一致";
    case "majority": return "多數決";
    case "any": return "任一觸發";
    default: return mode;
  }
}

function getModeDescription(mode: string, count: number): string {
  switch (mode) {
    case "all": return `${count} 個指標必須同時發出買進/賣出訊號才會執行`;
    case "majority": return `超過半數指標（>${Math.floor(count / 2)}個）發出訊號即執行`;
    case "any": return `任一指標發出訊號就執行`;
    default: return "";
  }
}

/* ══════════════════════════════════════════════════════════════════
   Main Component: B+C layout
   ══════════════════════════════════════════════════════════════════ */

export function BacktestHistory() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const { data: allData, isLoading } = useBacktestHistory(undefined, 200);

  // Derive distinct symbols with summary stats
  const symbolList = useMemo(() => {
    if (!allData?.results?.length) return [];
    const map = new Map<string, { count: number; bestReturn: number; bestSharpe: number }>();
    for (const r of allData.results) {
      const existing = map.get(r.symbol);
      if (!existing) {
        map.set(r.symbol, { count: 1, bestReturn: r.total_return, bestSharpe: r.sharpe_ratio });
      } else {
        existing.count++;
        if (r.total_return > existing.bestReturn) existing.bestReturn = r.total_return;
        if (r.sharpe_ratio > existing.bestSharpe) existing.bestSharpe = r.sharpe_ratio;
      }
    }
    return Array.from(map.entries())
      .map(([symbol, stats]) => ({ symbol, ...stats }))
      .sort((a, b) => b.bestReturn - a.bestReturn);
  }, [allData]);

  // Auto-select first symbol
  const activeSymbol = selectedSymbol ?? symbolList[0]?.symbol ?? null;

  // Filter results for selected symbol
  const symbolResults = useMemo(() => {
    if (!activeSymbol || !allData?.results) return [];
    return allData.results
      .filter((r) => r.symbol === activeSymbol)
      .sort((a, b) => b.total_return - a.total_return);
  }, [activeSymbol, allData]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (symbolList.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <div className="text-center">
          <div className="text-4xl mb-3 opacity-30">📊</div>
          <p className="text-[var(--text-muted)] text-sm">尚無回測紀錄</p>
          <p className="text-[var(--text-muted)] text-xs mt-1">在「策略建構」執行回測後結果會顯示在這裡</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-4 animate-fade-in min-h-[500px]">
      {/* ── Left: Symbol List ── */}
      <div className="w-48 shrink-0">
        <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-2">
          回測標的
        </p>
        <div className="space-y-1">
          {symbolList.map((s) => (
            <button
              key={s.symbol}
              onClick={() => setSelectedSymbol(s.symbol)}
              className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all duration-200 ${
                activeSymbol === s.symbol
                  ? "bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30"
                  : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] hover:bg-[var(--card-hover)]"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[var(--foreground)] text-sm font-medium mono-nums">{s.symbol}</span>
                <span className="text-[10px] text-[var(--text-muted)] mono-nums">{s.count} 筆</span>
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`text-[10px] mono-nums ${s.bestReturn >= 0 ? "text-[var(--stock-down)]" : "text-[var(--stock-up)]"}`}>
                  最高 {fmtPct(s.bestReturn)}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* ── Right: Dashboard (C layout) ── */}
      <div className="flex-1 min-w-0">
        {activeSymbol && symbolResults.length > 0 ? (
          <SymbolDashboard symbol={activeSymbol} results={symbolResults} />
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-[var(--text-muted)] text-sm">選擇左側標的查看回測結果</p>
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   Symbol Dashboard (C layout)
   ══════════════════════════════════════════════════════════════════ */

function SymbolDashboard({ symbol, results }: { symbol: string; results: BacktestHistoryItem[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("total_return");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const best = results[0]; // already sorted by return desc
  const totalCombos = results.length;

  const sorted = useMemo(() => {
    return [...results].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      return sortDir === "asc" ? aVal - bVal : bVal - aVal;
    });
  }, [results, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  // Parse strategy signals for human-readable display
  const bestParams = best.strategy_params || {};
  const { mode: bestMode, rules: bestRules } = parseStrategySignals(bestParams);

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-bold text-[var(--foreground)] mono-nums">{symbol}</h3>
          <p className="text-xs text-[var(--text-muted)]">
            共測試 <span className="mono-nums text-[var(--foreground)]">{totalCombos}</span> 種策略組合
          </p>
        </div>
        <button
          onClick={() => {
            const csvData = results.map((r) => ({
              策略名稱: r.strategy_name,
              標的: r.symbol,
              總報酬率: r.total_return,
              年化報酬率: r.annualized_return,
              勝率: r.win_rate,
              Sharpe: r.sharpe_ratio,
              最大回撤: r.max_drawdown,
              獲利因子: r.profit_factor,
              交易次數: r.total_trades,
            }));
            downloadCSV(csvData, `backtest_${symbol}_${new Date().toISOString().slice(0, 10)}.csv`);
          }}
          className="text-[10px] px-2 py-1 rounded border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--foreground)] hover:border-[var(--accent-blue)] transition-colors"
        >
          ↓ 匯出 CSV
        </button>
      </div>

      {/* ── Best Strategy Highlight Card ── */}
      <div className="bg-gradient-to-r from-[var(--accent-blue)]/5 to-transparent border border-[var(--accent-blue)]/20 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-blue)]">🏆 最佳策略</span>
          {bestMode && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--accent-blue)]/10 text-[var(--accent-blue)]">
              判斷模式：{getModeLabel(bestMode)}
            </span>
          )}
        </div>

        {/* Big metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">總報酬率</p>
            <p className={`text-2xl font-bold mono-nums ${best.total_return >= 0 ? "text-[var(--stock-down)] glow-green" : "text-[var(--stock-up)] glow-red"}`}>
              {fmtPct(best.total_return)}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">年化報酬率</p>
            <p className={`text-2xl font-bold mono-nums ${best.annualized_return >= 0 ? "text-[var(--stock-down)]" : "text-[var(--stock-up)]"}`}>
              {fmtPct(best.annualized_return)}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">勝率</p>
            <p className="text-2xl font-bold mono-nums text-[var(--foreground)]">{fmtNum(best.win_rate, 1)}%</p>
          </div>
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">Sharpe</p>
            <p className="text-2xl font-bold mono-nums text-[var(--foreground)]">{fmtNum(best.sharpe_ratio, 4)}</p>
          </div>
        </div>

        {/* Secondary metrics */}
        <div className="grid grid-cols-3 gap-3 mt-3 pt-3 border-t border-[var(--border-subtle)]">
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">最大回撤</p>
            <p className="text-sm font-semibold mono-nums text-[var(--stock-up)]">{fmtNum(best.max_drawdown, 2)}%</p>
          </div>
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">獲利因子</p>
            <p className="text-sm font-semibold mono-nums text-[var(--text-secondary)]">{fmtNum(best.profit_factor, 2)}</p>
          </div>
          <div>
            <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">交易次數</p>
            <p className="text-sm font-semibold mono-nums text-[var(--text-secondary)]">{best.total_trades}</p>
          </div>
        </div>

        {/* ── Entry/Exit Signal Explanation ── */}
        {bestRules.length > 0 && (
          <div className="mt-4 pt-4 border-t border-[var(--border-subtle)]">
            {bestMode && (
              <div className="mb-3 px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)]">
                <p className="text-xs text-[var(--text-secondary)]">
                  <span className="text-[var(--accent-blue)] font-medium">複合判斷：</span>
                  {getModeDescription(bestMode, bestRules.length)}
                </p>
              </div>
            )}
            <div className="space-y-2">
              {bestRules.map((rule, idx) => (
                <div key={idx} className="rounded-lg border border-[var(--border-subtle)] overflow-hidden">
                  <div className="px-3 py-1.5 bg-[var(--bg-secondary)]">
                    <span className="text-xs font-medium text-[var(--foreground)]">{rule.indicator}</span>
                  </div>
                  <div className="px-3 py-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div className="flex items-start gap-2">
                      <span className="shrink-0 mt-0.5 w-4 h-4 rounded flex items-center justify-center text-[10px] font-bold bg-[var(--stock-down)]/15 text-[var(--stock-down)]">
                        買
                      </span>
                      <p className="text-xs text-[var(--text-secondary)]">{rule.buy}</p>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="shrink-0 mt-0.5 w-4 h-4 rounded flex items-center justify-center text-[10px] font-bold bg-[var(--stock-up)]/15 text-[var(--stock-up)]">
                        賣
                      </span>
                      <p className="text-xs text-[var(--text-secondary)]">{rule.sell}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Trade Log in Best Card ── */}
        {best.trade_log && best.trade_log.length > 0 && (
          <TradeLogTable trades={best.trade_log} />
        )}
      </div>

      {/* ── Strategy Analysis + Comparison ── */}
      {results.length >= 3 && (
        <StrategyAnalysis results={results} />
      )}

      {/* ── Strategy Ranking Table ── */}
      <div>
        <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-2">
          策略排行榜
        </p>
        <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[var(--text-muted)] text-[10px] uppercase tracking-wider bg-[var(--bg-secondary)]">
                <th className="py-2 px-3 font-medium w-8">#</th>
                <th className="py-2 px-3 font-medium">策略</th>
                <SortableHeader label="報酬率" sortKey="total_return" currentKey={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="勝率" sortKey="win_rate" currentKey={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="Sharpe" sortKey="sharpe_ratio" currentKey={sortKey} dir={sortDir} onSort={handleSort} />
                <SortableHeader label="交易" sortKey="total_trades" currentKey={sortKey} dir={sortDir} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry, i) => {
                const isPositive = entry.total_return >= 0;
                const isExpanded = expandedId === entry.id;
                const isTop3 = i < 3 && sortKey === "total_return" && sortDir === "desc";

                return (
                  <tr
                    key={entry.id}
                    onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                    className={`border-t border-[var(--border-subtle)] cursor-pointer transition-colors duration-100 hover:bg-[var(--card-hover)] ${
                      isTop3 ? "bg-[var(--accent-blue)]/[0.03]" : i % 2 === 0 ? "" : "bg-[var(--bg-secondary)]/30"
                    }`}
                  >
                    <td className="py-2 px-3 mono-nums text-[var(--text-muted)]">
                      {isTop3 ? (
                        <span className="text-[var(--accent-blue)]">{["🥇", "🥈", "🥉"][i]}</span>
                      ) : (
                        <span>{i + 1}</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-[var(--text-secondary)] max-w-[300px] truncate" title={entry.strategy_name}>
                      {entry.strategy_name}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <Badge variant={isPositive ? "down" : "up"}>
                        <span className="mono-nums">{fmtPct(entry.total_return)}</span>
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-right mono-nums text-[var(--text-secondary)]">
                      {fmtNum(entry.win_rate, 1)}%
                    </td>
                    <td className="py-2 px-3 text-right mono-nums text-[var(--text-secondary)]">
                      {fmtNum(entry.sharpe_ratio, 4)}
                    </td>
                    <td className="py-2 px-3 text-right mono-nums text-[var(--text-muted)]">
                      {entry.total_trades}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Expanded Detail ── */}
      {expandedId !== null && (
        <ExpandedStrategyDetail
          entry={sorted.find((e) => e.id === expandedId)!}
          onClose={() => setExpandedId(null)}
        />
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   Sub-components
   ══════════════════════════════════════════════════════════════════ */

function SortableHeader({
  label,
  sortKey,
  currentKey,
  dir,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  currentKey: SortKey;
  dir: "asc" | "desc";
  onSort: (key: SortKey) => void;
}) {
  return (
    <th
      className="py-2 px-3 font-medium cursor-pointer select-none hover:text-[var(--foreground)] transition-colors text-right"
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {currentKey === sortKey && (
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 12 12">
            {dir === "asc" ? <path d="M6 3l4 5H2z" /> : <path d="M6 9l4-5H2z" />}
          </svg>
        )}
      </span>
    </th>
  );
}

function ExpandedStrategyDetail({ entry, onClose }: { entry: BacktestHistoryItem; onClose: () => void }) {
  if (!entry) return null;

  const params = entry.strategy_params || {};
  const { mode, rules } = parseStrategySignals(params);

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4 animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-sm font-medium text-[var(--foreground)]">{entry.strategy_name}</p>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            {entry.symbol} · {entry.created_at.split("T")[0]}
            {mode && <> · 判斷模式：{getModeLabel(mode)}</>}
          </p>
        </div>
        <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors" aria-label="Close">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <MetricCell label="報酬率" value={fmtPct(entry.total_return)} positive={entry.total_return >= 0} />
        <MetricCell label="年化" value={fmtPct(entry.annualized_return)} positive={entry.annualized_return >= 0} />
        <MetricCell label="最大回撤" value={fmtNum(entry.max_drawdown, 2) + "%"} positive={false} />
        <MetricCell label="勝率" value={fmtNum(entry.win_rate, 1) + "%"} />
        <MetricCell label="Sharpe" value={fmtNum(entry.sharpe_ratio, 4)} />
        <MetricCell label="獲利因子" value={fmtNum(entry.profit_factor, 2)} />
        <MetricCell label="交易次數" value={String(entry.total_trades)} />
      </div>

      {/* Entry/Exit explanation */}
      {rules.length > 0 && (
        <div className="space-y-1.5">
          {rules.map((rule, idx) => (
            <div key={idx} className="flex items-center gap-3 text-xs">
              <span className="text-[var(--text-muted)] shrink-0 w-28">{rule.indicator}</span>
              <span className="text-[var(--stock-down)]">買：{rule.buy.split("進場")[0]}</span>
              <span className="text-[var(--text-muted)]">|</span>
              <span className="text-[var(--stock-up)]">賣：{rule.sell.split("出場")[0]}</span>
            </div>
          ))}
        </div>
      )}

      {/* Trade log */}
      {entry.trade_log && entry.trade_log.length > 0 && (
        <TradeLogTable trades={entry.trade_log} />
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   Strategy Analysis & Comparison
   ══════════════════════════════════════════════════════════════════ */

interface StrategyProfile {
  label: string;
  tagColor: string;
  tagBg: string;
  description: string;
  entry: BacktestHistoryItem | null;
}

function StrategyAnalysis({ results }: { results: BacktestHistoryItem[] }) {
  // Classify strategies into 3 profiles
  const aggressive = results.reduce((best, r) =>
    r.total_return > (best?.total_return ?? -Infinity) && r.total_trades >= 20 ? r : best,
    null as BacktestHistoryItem | null
  );

  const conservative = results.reduce((best, r) =>
    r.win_rate >= 90 && r.total_return > (best?.total_return ?? -Infinity) ? r : best,
    null as BacktestHistoryItem | null
  );

  const balanced = results.reduce((best, r) => {
    if (r.total_trades < 8 || r.total_trades > 30) return best;
    if (r.win_rate < 70) return best;
    const score = r.total_return * 0.4 + r.win_rate * 5 + r.sharpe_ratio * 100;
    const bestScore = best ? best.total_return * 0.4 + best.win_rate * 5 + best.sharpe_ratio * 100 : -Infinity;
    return score > bestScore ? r : best;
  }, null as BacktestHistoryItem | null);

  const profiles: StrategyProfile[] = [
    {
      label: "積極型",
      tagColor: "text-orange-400",
      tagBg: "bg-orange-400/10 border-orange-400/20",
      description: "追求最高報酬，交易頻繁，願意承受較高風險和回撤",
      entry: aggressive,
    },
    {
      label: "穩健型",
      tagColor: "text-emerald-400",
      tagBg: "bg-emerald-400/10 border-emerald-400/20",
      description: "優先保護本金，只在高確定性時進場，勝率極高但交易機會少",
      entry: conservative,
    },
    {
      label: "平衡型",
      tagColor: "text-blue-400",
      tagBg: "bg-blue-400/10 border-blue-400/20",
      description: "兼顧報酬與風險，適度交易頻率，勝率與報酬都在合理範圍",
      entry: balanced,
    },
  ].filter(p => p.entry !== null);

  if (profiles.length < 2) return null;

  // Analysis text
  const bestReturn = aggressive;
  const bestWinRate = conservative;
  const hasMultiIndicator = results.some(r => {
    const p = r.strategy_params;
    const indicators = [p.rsi_period || p.rsi_buy, p.bias_period || p.bias_buy, p.bb_period || p.bb_std, p.macd_fast].filter(Boolean);
    return indicators.length >= 2;
  });

  return (
    <div className="space-y-4">
      {/* Analysis */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-blue)]">📊 策略分析</span>
        </div>
        <div className="space-y-2 text-xs text-[var(--text-secondary)] leading-relaxed">
          {bestReturn && bestWinRate && bestReturn.id !== bestWinRate.id && (
            <p>
              報酬率最高的策略（<span className="text-[var(--foreground)] mono-nums">{fmtPct(bestReturn.total_return)}</span>）
              勝率為 <span className="mono-nums text-[var(--foreground)]">{fmtNum(bestReturn.win_rate, 1)}%</span>，
              共交易 <span className="mono-nums text-[var(--foreground)]">{bestReturn.total_trades}</span> 次。
              而勝率最高的策略（<span className="text-[var(--foreground)] mono-nums">{fmtNum(bestWinRate.win_rate, 1)}%</span>）
              報酬為 <span className="mono-nums text-[var(--foreground)]">{fmtPct(bestWinRate.total_return)}</span>，
              交易僅 <span className="mono-nums text-[var(--foreground)]">{bestWinRate.total_trades}</span> 次。
              <span className="text-[var(--text-muted)]"> — 高報酬與高勝率往往難以兼得，需依風險偏好選擇。</span>
            </p>
          )}
          {hasMultiIndicator && (
            <p>
              多指標複合策略（RSI+乖離率+布林通道）使用 <span className="text-[var(--foreground)]">[全部一致]</span> 模式時勝率最高，
              因為三個指標同時確認才進場，大幅過濾假訊號。
              但交易機會較少 — 適合有耐心等待的投資人。
            </p>
          )}
          <p className="text-[var(--text-muted)]">
            以下依投資風格分為三種策略類型，供參考選擇：
          </p>
        </div>
      </div>

      {/* Comparison Table */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent-blue)]">⚖️ 策略風格對照表</span>
        </div>

        {/* Header */}
        <div className="grid grid-cols-4 gap-3 mb-2">
          <div />
          {profiles.map((p) => (
            <div key={p.label} className="text-center">
              <span className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded border ${p.tagBg} ${p.tagColor}`}>
                {p.label}
              </span>
            </div>
          ))}
        </div>

        {/* Rows */}
        {[
          { label: "策略", render: (e: BacktestHistoryItem) => e.strategy_name.length > 30 ? e.strategy_name.slice(0, 28) + "..." : e.strategy_name },
          { label: "總報酬率", render: (e: BacktestHistoryItem) => fmtPct(e.total_return), highlight: true },
          { label: "年化報酬", render: (e: BacktestHistoryItem) => fmtPct(e.annualized_return) },
          { label: "最大回撤", render: (e: BacktestHistoryItem) => fmtNum(e.max_drawdown, 2) + "%", negative: true },
          { label: "勝率", render: (e: BacktestHistoryItem) => fmtNum(e.win_rate, 1) + "%" },
          { label: "Sharpe", render: (e: BacktestHistoryItem) => fmtNum(e.sharpe_ratio, 4) },
          { label: "交易次數", render: (e: BacktestHistoryItem) => String(e.total_trades) },
          { label: "獲利因子", render: (e: BacktestHistoryItem) => fmtNum(e.profit_factor, 2) },
        ].map((row) => (
          <div
            key={row.label}
            className="grid grid-cols-4 gap-3 py-2 border-t border-[var(--border-subtle)] items-center"
          >
            <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium">{row.label}</div>
            {profiles.map((p) => {
              const e = p.entry!;
              const val = row.render(e);
              const isStrategy = row.label === "策略";
              const isHighlight = row.highlight;
              const isNegative = row.negative;
              return (
                <div key={p.label} className="text-center">
                  <span
                    className={`text-xs mono-nums ${
                      isStrategy
                        ? "text-[var(--text-secondary)] text-[10px] break-all"
                        : isHighlight
                        ? parseFloat(val) >= 0
                          ? "text-[var(--stock-down)] font-bold text-sm"
                          : "text-[var(--stock-up)] font-bold text-sm"
                        : isNegative
                        ? "text-[var(--stock-up)]"
                        : "text-[var(--foreground)]"
                    }`}
                    title={isStrategy ? e.strategy_name : undefined}
                  >
                    {val}
                  </span>
                </div>
              );
            })}
          </div>
        ))}

        {/* Recommendation */}
        <div className="mt-4 pt-3 border-t border-[var(--border-subtle)] grid grid-cols-4 gap-3">
          <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium">適合對象</div>
          {profiles.map((p) => (
            <div key={p.label} className="text-center">
              <p className="text-[10px] text-[var(--text-muted)] leading-relaxed">{p.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function TradeLogTable({ trades }: { trades: TradeLogEntry[] }) {
  const buyCount = trades.filter((t) => t.action === "BUY").length;
  const sellCount = trades.filter((t) => t.action === "SELL" || t.action === "SELL(force)").length;

  return (
    <div className="mt-4 pt-4 border-t border-[var(--border-subtle)]">
      <div className="flex items-center gap-3 mb-2">
        <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium">交易紀錄</p>
        <div className="flex items-center gap-2 text-[10px]">
          <span className="px-1.5 py-0.5 rounded bg-[var(--stock-down)]/15 text-[var(--stock-down)] mono-nums">
            買進 {buyCount} 次
          </span>
          <span className="px-1.5 py-0.5 rounded bg-[var(--stock-up)]/15 text-[var(--stock-up)] mono-nums">
            賣出 {sellCount} 次
          </span>
          <span className="text-[var(--text-muted)] mono-nums">
            共 {trades.length} 筆
          </span>
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[var(--text-muted)] text-[10px] uppercase tracking-wider bg-[var(--bg-secondary)]">
              <th className="py-1.5 px-3 font-medium">日期</th>
              <th className="py-1.5 px-3 font-medium">動作</th>
              <th className="py-1.5 px-3 font-medium text-right">價格</th>
              <th className="py-1.5 px-3 font-medium text-right">股數</th>
              <th className="py-1.5 px-3 font-medium">觸發原因</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => {
              const isBuy = t.action === "BUY";
              return (
                <tr
                  key={i}
                  className={`border-t border-[var(--border-subtle)] ${i % 2 === 0 ? "" : "bg-[var(--bg-secondary)]/30"}`}
                >
                  <td className="py-1.5 px-3 mono-nums text-[var(--text-secondary)]">{t.date}</td>
                  <td className="py-1.5 px-3">
                    <span
                      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        isBuy
                          ? "text-[var(--stock-down)] bg-[var(--stock-down)]/15"
                          : "text-[var(--stock-up)] bg-[var(--stock-up)]/15"
                      }`}
                    >
                      {isBuy ? "買進" : "賣出"}
                    </span>
                  </td>
                  <td className="py-1.5 px-3 text-right mono-nums text-[var(--foreground)]">{t.price.toFixed(2)}</td>
                  <td className="py-1.5 px-3 text-right mono-nums text-[var(--text-secondary)]">{t.shares.toLocaleString()}</td>
                  <td className="py-1.5 px-3 text-[var(--text-muted)] max-w-[250px] truncate" title={t.reason}>{t.reason}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MetricCell({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  const colorClass = positive === true ? "text-[var(--stock-down)]" : positive === false ? "text-[var(--stock-up)]" : "text-[var(--text-secondary)]";
  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-2.5">
      <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5">{label}</p>
      <p className={`text-sm font-bold mono-nums ${colorClass}`}>{value}</p>
    </div>
  );
}
