"use client";

import type { PortfolioBacktestResult } from "@/hooks/use-portfolio";

const STOCK_COLORS = [
  "#8b5cf6", // purple
  "#f59e0b", // amber
  "#22c55e", // green
  "#ef4444", // red
  "#06b6d4", // cyan
];

const PORTFOLIO_COLOR = "#3b82f6";

function formatPct(v: number): string {
  return (v * 100).toFixed(2) + "%";
}

function formatMoney(v: number): string {
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

/* ── Multi-line Equity Chart ── */

function ComparisonChart({ result }: { result: PortfolioBacktestResult }) {
  const W = 840;
  const H = 340;
  const PAD_L = 56;
  const PAD_R = 24;
  const PAD_T = 24;
  const PAD_B = 36;

  // Collect all values to find global min/max
  const allValues: number[] = [...result.portfolio_equity];
  const symbols = Object.keys(result.stock_equities);
  symbols.forEach((sym) => {
    allValues.push(...result.stock_equities[sym]);
  });

  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 0.01;
  const days = result.portfolio_equity.length;

  const toX = (i: number) => PAD_L + (i / (days - 1)) * (W - PAD_L - PAD_R);
  const toY = (v: number) => H - PAD_B - ((v - min) / range) * (H - PAD_T - PAD_B);

  const buildPolyline = (data: number[]) =>
    data.map((v, i) => `${toX(i)},${toY(v)}`).join(" ");

  // Grid lines
  const gridCount = 5;
  const gridLines = Array.from({ length: gridCount + 1 }, (_, i) => {
    const y = PAD_T + (i / gridCount) * (H - PAD_T - PAD_B);
    const val = max - (i / gridCount) * range;
    return { y, label: val >= 1 ? formatMoney(val * 100) + "%" : (val * 100).toFixed(0) + "%" };
  });

  // X-axis labels (show ~5)
  const xLabels = Array.from({ length: 5 }, (_, i) => {
    const idx = Math.floor((i / 4) * (days - 1));
    return { x: toX(idx), label: result.dates[idx]?.slice(5) || "" };
  });

  // Portfolio gradient fill
  const portfolioPoints = buildPolyline(result.portfolio_equity);
  const firstX = toX(0);
  const lastX = toX(days - 1);
  const bottomY = H - PAD_B;
  const fillPath = `M${firstX},${bottomY} L${portfolioPoints.split(" ").join(" L")} L${lastX},${bottomY} Z`;

  return (
    <div className="bg-[var(--background)] border border-[var(--border-subtle)] rounded-lg p-4">
      <h3 className="text-xs font-semibold mb-3 text-[var(--text-secondary)] uppercase tracking-wider">
        權益曲線比較
      </h3>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mb-3">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 rounded-full" style={{ backgroundColor: PORTFOLIO_COLOR }} />
          <span className="text-[10px] text-[var(--text-secondary)] font-medium">組合</span>
        </div>
        {symbols.map((sym, i) => (
          <div key={sym} className="flex items-center gap-1.5">
            <div
              className="w-3 h-0.5 rounded-full"
              style={{ backgroundColor: STOCK_COLORS[i % STOCK_COLORS.length] }}
            />
            <span className="text-[10px] text-[var(--text-muted)] mono-nums">{sym}</span>
          </div>
        ))}
      </div>

      <div className="w-full overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full max-w-4xl"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Portfolio comparison equity curve chart"
        >
          <defs>
            <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={PORTFOLIO_COLOR} stopOpacity="0.2" />
              <stop offset="100%" stopColor={PORTFOLIO_COLOR} stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Grid */}
          {gridLines.map((g, i) => (
            <g key={i}>
              <line
                x1={PAD_L}
                y1={g.y}
                x2={W - PAD_R}
                y2={g.y}
                stroke="rgba(255,255,255,0.04)"
                strokeWidth="1"
              />
              <text
                x={PAD_L - 6}
                y={g.y + 3}
                textAnchor="end"
                fill="#475569"
                fontSize="9"
                fontFamily="monospace"
              >
                {g.label}
              </text>
            </g>
          ))}

          {/* X-axis labels */}
          {xLabels.map((xl, i) => (
            <text
              key={i}
              x={xl.x}
              y={H - 8}
              textAnchor="middle"
              fill="#475569"
              fontSize="9"
              fontFamily="monospace"
            >
              {xl.label}
            </text>
          ))}

          {/* Portfolio gradient fill */}
          <path d={fillPath} fill="url(#portfolioGradient)" />

          {/* Individual stock lines */}
          {symbols.map((sym, i) => (
            <polyline
              key={sym}
              fill="none"
              stroke={STOCK_COLORS[i % STOCK_COLORS.length]}
              strokeWidth="1.2"
              strokeOpacity="0.6"
              points={buildPolyline(result.stock_equities[sym])}
            />
          ))}

          {/* Portfolio line (on top, bold) */}
          <polyline
            fill="none"
            stroke={PORTFOLIO_COLOR}
            strokeWidth="2.5"
            points={portfolioPoints}
            style={{ filter: "drop-shadow(0 0 6px rgba(59, 130, 246, 0.5))" }}
          />

          {/* Baseline at 1.0 (100%) */}
          {min < 1 && max > 1 && (
            <line
              x1={PAD_L}
              y1={toY(1)}
              x2={W - PAD_R}
              y2={toY(1)}
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="1"
              strokeDasharray="4 4"
            />
          )}
        </svg>
      </div>
    </div>
  );
}

/* ── Metric Card (inline) ── */

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
  const display = isPercent ? formatPct(value) : value.toFixed(2);
  const positive = invertColor ? value <= 0 : value >= 0;
  const colorClass = positive ? "text-[var(--stock-down)]" : "text-[var(--stock-up)]";
  const glowClass = positive ? "glow-green" : "glow-red";

  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-3 transition-colors duration-150 hover:bg-[var(--card-hover)]">
      <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-wider font-medium mb-1">
        {label}
      </p>
      <p className={`text-lg font-bold mono-nums ${colorClass} ${glowClass}`}>{display}</p>
    </div>
  );
}

/* ── Stock Metrics Table ── */

function StockMetricsTable({ result }: { result: PortfolioBacktestResult }) {
  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
      <h3 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">
        個股績效明細
      </h3>
      <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[var(--text-muted)] text-[10px] uppercase tracking-wider bg-[var(--bg-secondary)]">
              <th className="py-2 px-3 font-medium">標的</th>
              <th className="py-2 px-3 font-medium text-right">權重</th>
              <th className="py-2 px-3 font-medium text-right">總報酬</th>
              <th className="py-2 px-3 font-medium text-right">夏普</th>
              <th className="py-2 px-3 font-medium text-right">勝率</th>
              <th className="py-2 px-3 font-medium text-right">最大回撤</th>
            </tr>
          </thead>
          <tbody>
            {result.stock_metrics.map((m, i) => {
              const retColor = m.total_return >= 0 ? "text-[var(--stock-down)]" : "text-[var(--stock-up)]";
              return (
                <tr
                  key={m.symbol}
                  className={`border-t border-[var(--border-subtle)] transition-colors duration-100 hover:bg-[var(--card-hover)] ${
                    i % 2 === 0 ? "" : "bg-[var(--bg-secondary)]/30"
                  }`}
                >
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-1.5">
                      <div
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: STOCK_COLORS[i % STOCK_COLORS.length] }}
                      />
                      <span className="mono-nums text-[var(--foreground)] font-medium">{m.symbol}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 mono-nums text-[var(--text-secondary)] text-right">
                    {m.weight.toFixed(0)}%
                  </td>
                  <td className={`py-2 px-3 mono-nums text-right font-medium ${retColor}`}>
                    {formatPct(m.total_return)}
                  </td>
                  <td className="py-2 px-3 mono-nums text-[var(--text-secondary)] text-right">
                    {m.sharpe_ratio.toFixed(2)}
                  </td>
                  <td className="py-2 px-3 mono-nums text-[var(--text-secondary)] text-right">
                    {formatPct(m.win_rate)}
                  </td>
                  <td className="py-2 px-3 mono-nums text-[var(--stock-up)] text-right">
                    {formatPct(m.max_drawdown)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Rebalance Log ── */

function RebalanceLog({ result }: { result: PortfolioBacktestResult }) {
  if (result.rebalance_log.length === 0) return null;

  return (
    <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
      <h3 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">
        再平衡紀錄
      </h3>
      <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[var(--text-muted)] text-[10px] uppercase tracking-wider bg-[var(--bg-secondary)]">
              <th className="py-2 px-3 font-medium">日期</th>
              <th className="py-2 px-3 font-medium">原因</th>
              <th className="py-2 px-3 font-medium">調整</th>
            </tr>
          </thead>
          <tbody>
            {result.rebalance_log.map((event, i) => (
              <tr
                key={i}
                className={`border-t border-[var(--border-subtle)] transition-colors duration-100 hover:bg-[var(--card-hover)] ${
                  i % 2 === 0 ? "" : "bg-[var(--bg-secondary)]/30"
                }`}
              >
                <td className="py-2 px-3 mono-nums text-[var(--text-secondary)]">{event.date}</td>
                <td className="py-2 px-3 text-[var(--text-muted)]">{event.reason}</td>
                <td className="py-2 px-3">
                  <div className="flex flex-wrap gap-1">
                    {event.adjustments.map((adj, j) => (
                      <span
                        key={j}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-secondary)] border border-[var(--border-subtle)] mono-nums"
                      >
                        <span className="text-[var(--foreground)] font-medium">{adj.symbol}</span>
                        <span className="text-[var(--text-muted)] mx-1">
                          {adj.from_weight.toFixed(1)}%
                        </span>
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none" className="mx-0.5">
                          <path d="M1 4h6M5 2l2 2-2 2" stroke="#64748b" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        <span className="text-[var(--accent-blue)]">
                          {adj.to_weight.toFixed(1)}%
                        </span>
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Main Export ── */

interface PortfolioComparisonProps {
  result: PortfolioBacktestResult;
  initialCapital: number;
}

export function PortfolioComparison({ result, initialCapital }: PortfolioComparisonProps) {
  const finalValue = result.portfolio_equity[result.portfolio_equity.length - 1] * initialCapital;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Portfolio Metrics */}
      <div>
        <h2 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">
          組合績效
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <MetricCard label="總報酬率" value={result.total_return} isPercent />
          <MetricCard label="年化報酬率" value={result.annualized_return} isPercent />
          <MetricCard label="最大回撤" value={result.max_drawdown} isPercent invertColor />
          <MetricCard label="夏普比率" value={result.sharpe_ratio} />
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-3">
            <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-wider font-medium mb-1">
              初始資金
            </p>
            <p className="text-lg font-bold mono-nums text-[var(--foreground)]">
              ${formatMoney(initialCapital)}
            </p>
          </div>
          <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-3">
            <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-wider font-medium mb-1">
              最終價值
            </p>
            <p className={`text-lg font-bold mono-nums ${finalValue >= initialCapital ? "text-[var(--stock-down)] glow-green" : "text-[var(--stock-up)] glow-red"}`}>
              ${formatMoney(finalValue)}
            </p>
          </div>
        </div>
      </div>

      {/* Comparison Chart */}
      <ComparisonChart result={result} />

      {/* Stock Metrics Table */}
      <StockMetricsTable result={result} />

      {/* Rebalance Log */}
      <RebalanceLog result={result} />
    </div>
  );
}
