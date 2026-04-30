"use client";

import { type BacktestResult } from "@/lib/api-client";
import { EquityChart } from "./equity-chart";

/* ---------- Helpers ---------- */

function formatPct(v: number): string {
  return (v * 100).toFixed(2) + "%";
}

function formatNum(v: number, decimals = 2): string {
  return v.toFixed(decimals);
}

/* ---------- MetricCard ---------- */

function MetricCard({
  label,
  value,
  isPercent,
  invertColor,
}: {
  label: string;
  value: number;
  isPercent?: boolean;
  invertColor?: boolean;
}) {
  const display = isPercent ? formatPct(value) : formatNum(value);
  const positive = invertColor ? value <= 0 : value >= 0;
  const colorClass = positive
    ? "text-[var(--stock-down)]"
    : "text-[var(--stock-up)]";
  const glowClass = positive ? "glow-green" : "glow-red";

  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-3 transition-colors duration-150 hover:bg-[var(--card-hover)]">
      <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-wider font-medium mb-1">
        {label}
      </p>
      <p className={`text-lg font-bold mono-nums ${colorClass} ${glowClass}`}>
        {display}
      </p>
    </div>
  );
}

/* ---------- Main ---------- */

interface BacktestResultsProps {
  result: BacktestResult | null;
}

export function BacktestResults({ result }: BacktestResultsProps) {
  if (!result) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <p className="text-[var(--text-muted)] text-sm">
          尚無回測結果 -- 請先執行回測
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-medium text-[var(--foreground)] mono-nums">
          {result.symbol}
        </span>
        <span className="text-xs text-[var(--text-muted)]">{result.strategy}</span>
      </div>

      {/* Metrics */}
      <div>
        <h2 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">
          績效指標
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <MetricCard label="總報酬率" value={result.metrics.total_return} isPercent />
          <MetricCard label="年化報酬率" value={result.metrics.annualized_return} isPercent />
          <MetricCard label="最大回撤" value={result.metrics.max_drawdown} isPercent invertColor />
          <MetricCard label="夏普比率" value={result.metrics.sharpe_ratio} />
          <MetricCard label="勝率" value={result.metrics.win_rate} isPercent />
          <MetricCard label="交易次數" value={result.metrics.total_trades} />
          <MetricCard label="盈虧比" value={result.metrics.profit_factor} />
        </div>
      </div>

      {/* Equity Curve */}
      <div className="bg-[var(--background)] border border-[var(--border-subtle)] rounded-lg p-4">
        <EquityChart data={result.equity_curve} label="權益曲線" />
      </div>

      {/* Trade Log */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
        <h3 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">
          交易紀錄
        </h3>
        {result.trades.length === 0 ? (
          <p className="text-[var(--text-muted)] text-xs">無交易紀錄</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[var(--text-muted)] text-[10px] uppercase tracking-wider bg-[var(--bg-secondary)]">
                  <th className="py-2 px-3 font-medium">日期</th>
                  <th className="py-2 px-3 font-medium">動作</th>
                  <th className="py-2 px-3 font-medium">價格</th>
                  <th className="py-2 px-3 font-medium">股數</th>
                  <th className="py-2 px-3 font-medium">原因</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.map((trade, i) => {
                  const isBuy = trade.action.toUpperCase() === "BUY";
                  return (
                    <tr
                      key={i}
                      className={`border-t border-[var(--border-subtle)] transition-colors duration-100 hover:bg-[var(--card-hover)] ${
                        i % 2 === 0 ? "" : "bg-[var(--bg-secondary)]/30"
                      }`}
                    >
                      <td className="py-2 px-3 mono-nums text-[var(--text-secondary)]">
                        {trade.date}
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            isBuy
                              ? "text-[var(--stock-down)] bg-[var(--stock-down-bg)]"
                              : "text-[var(--stock-up)] bg-[var(--stock-up-bg)]"
                          }`}
                        >
                          {isBuy ? "買進" : "賣出"}
                        </span>
                      </td>
                      <td className="py-2 px-3 mono-nums text-[var(--foreground)]">
                        {formatNum(trade.price)}
                      </td>
                      <td className="py-2 px-3 mono-nums text-[var(--text-secondary)]">
                        {trade.shares.toLocaleString()}
                      </td>
                      <td className="py-2 px-3 text-[var(--text-muted)]">
                        {trade.reason}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
