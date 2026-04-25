"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/i18n/context";
import {
  fetchStrategies,
  runBacktest,
  type StrategyInfo,
  type BacktestResult,
} from "@/lib/api-client";

function formatPct(v: number): string {
  return (v * 100).toFixed(2) + "%";
}

function formatMoney(v: number): string {
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function formatNum(v: number, decimals = 2): string {
  return v.toFixed(decimals);
}

/* ---------- SVG Equity Curve ---------- */

function EquityCurve({ data, label }: { data: number[]; label: string }) {
  if (data.length < 2) return null;

  const W = 800;
  const H = 300;
  const PAD = 40;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = PAD + (i / (data.length - 1)) * (W - PAD * 2);
      const y = H - PAD - ((v - min) / range) * (H - PAD * 2);
      return `${x},${y}`;
    })
    .join(" ");

  // Build the gradient fill path
  const firstX = PAD;
  const lastX = PAD + ((data.length - 1) / (data.length - 1)) * (W - PAD * 2);
  const fillPath = `M${firstX},${H - PAD} L${points.split(" ").join(" L")} L${lastX},${H - PAD} Z`;

  // Grid lines (4 horizontal)
  const gridLines = Array.from({ length: 5 }, (_, i) => {
    const y = PAD + (i / 4) * (H - PAD * 2);
    const val = max - (i / 4) * range;
    return { y, label: formatMoney(val) };
  });

  return (
    <div className="w-full overflow-x-auto">
      <h3 className="text-sm font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">{label}</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-3xl" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Grid - darker lines for Glint style */}
        {gridLines.map((g, i) => (
          <g key={i}>
            <line x1={PAD} y1={g.y} x2={W - PAD} y2={g.y} stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
            <text x={PAD - 4} y={g.y + 4} textAnchor="end" fill="#475569" fontSize="10" fontFamily="monospace">
              {g.label}
            </text>
          </g>
        ))}
        {/* Gradient fill */}
        <path d={fillPath} fill="url(#equityGradient)" />
        {/* Line */}
        <polyline fill="none" stroke="#3b82f6" strokeWidth="2" points={points} style={{ filter: "drop-shadow(0 0 4px rgba(59, 130, 246, 0.4))" }} />
      </svg>
    </div>
  );
}

/* ---------- Metric Card ---------- */

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
  const colorClass = positive ? "text-[var(--stock-down)]" : "text-[var(--stock-up)]";
  const glowClass = positive ? "glow-green" : "glow-red";

  return (
    <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-3 transition-colors duration-150 hover:bg-[var(--card-hover)]">
      <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-wider font-medium mb-1">{label}</p>
      <p className={`text-lg font-bold mono-nums ${colorClass} ${glowClass}`}>{display}</p>
    </div>
  );
}

/* ---------- Strategy Card ---------- */

function StrategyCard({
  strategy,
  selected,
  onClick,
}: {
  strategy: StrategyInfo;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`text-left p-3 rounded-lg border transition-all duration-200 ${
        selected
          ? "bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30 animate-shimmer"
          : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] hover:bg-[var(--card-hover)]"
      }`}
    >
      <div className="font-medium text-white text-xs mb-0.5">{strategy.name}</div>
      <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">{strategy.description}</div>
    </button>
  );
}

/* ---------- Main Page ---------- */

export default function BacktestPage() {
  const { t } = useI18n();

  // Form state
  const [symbol, setSymbol] = useState("");
  const [strategy, setStrategy] = useState("");
  const [initialCapital, setInitialCapital] = useState(1_000_000);
  const [positionSize, setPositionSize] = useState(0.1);

  // Data state
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStrategies()
      .then((list) => {
        setStrategies(list);
        if (list.length > 0) setStrategy(list[0].name);
      })
      .catch(() => {
        /* strategies endpoint unavailable */
      });
  }, []);

  const handleRun = async () => {
    if (!symbol.trim() || !strategy) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await runBacktest({
        symbol: symbol.trim().toUpperCase(),
        strategy,
        initial_capital: initialCapital,
        position_size: positionSize,
      });
      setResult(res);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      if (msg.toLowerCase().includes("insufficient") || msg.toLowerCase().includes("not enough")) {
        setError(t.backtest.insufficientData);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    "w-full px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-white text-sm placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200";

  return (
    <div className="p-3 md:p-4 max-w-7xl mx-auto animate-fade-in">
      <h1 className="text-xl md:text-2xl font-bold mb-4 text-white tracking-tight">{t.backtest.title}</h1>

      <div className="flex flex-col lg:flex-row gap-4 mb-4">
        {/* Configuration panel */}
        <div className="lg:w-[360px] lg:shrink-0">
          <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4 sticky top-20">
            <div className="space-y-3">
              {/* Symbol */}
              <div>
                <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
                  {t.backtest.symbol}
                </label>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  placeholder="e.g. 2330.TW, AAPL"
                  className={inputClass}
                />
              </div>

              {/* Strategy cards */}
              <div>
                <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
                  {t.backtest.strategy}
                </label>
                {strategies.length > 0 ? (
                  <div className="space-y-1.5 max-h-40 overflow-y-auto">
                    {strategies.map((s) => (
                      <StrategyCard
                        key={s.name}
                        strategy={s}
                        selected={strategy === s.name}
                        onClick={() => setStrategy(s.name)}
                      />
                    ))}
                  </div>
                ) : (
                  <select
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                    className={inputClass}
                  >
                    <option value="">--</option>
                  </select>
                )}
              </div>

              {/* Initial Capital */}
              <div>
                <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
                  {t.backtest.initialCapital}
                </label>
                <input
                  type="number"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(Number(e.target.value) || 0)}
                  className={`${inputClass} mono-nums`}
                />
              </div>

              {/* Position Size */}
              <div>
                <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1">
                  {t.backtest.positionSize}: <span className="mono-nums">{(positionSize * 100).toFixed(0)}%</span>
                </label>
                <input
                  type="range"
                  min="0.1"
                  max="1.0"
                  step="0.1"
                  value={positionSize}
                  onChange={(e) => setPositionSize(parseFloat(e.target.value))}
                  className="w-full accent-blue-500"
                />
                <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-0.5 mono-nums">
                  <span>10%</span>
                  <span>100%</span>
                </div>
              </div>
            </div>

            <button
              onClick={handleRun}
              disabled={loading || !symbol.trim() || !strategy}
              className="mt-4 w-full py-2.5 bg-[var(--accent-blue)] text-white text-sm rounded-lg hover:bg-[var(--accent-blue-hover)] transition-all duration-200 disabled:opacity-50 font-medium"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {t.backtest.running}
                </span>
              ) : (
                t.backtest.run
              )}
            </button>

            {error && (
              <div className="mt-2 px-3 py-2 bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 rounded-lg">
                <p className="text-red-400 text-xs">{error}</p>
              </div>
            )}
          </div>
        </div>

        {/* Results panel */}
        <div className="flex-1 min-w-0">
          {!result && !loading && (
            <div className="flex items-center justify-center h-full min-h-[300px]">
              <p className="text-[var(--text-muted)] text-sm">{t.backtest.noResults}</p>
            </div>
          )}

          {result && (
            <div className="space-y-4 animate-fade-in">
              {/* Metrics */}
              <div>
                <h2 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">{t.backtest.metrics}</h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <MetricCard label={t.backtest.totalReturn} value={result.metrics.total_return} isPercent />
                  <MetricCard label={t.backtest.annualizedReturn} value={result.metrics.annualized_return} isPercent />
                  <MetricCard label={t.backtest.maxDrawdown} value={result.metrics.max_drawdown} isPercent invertColor />
                  <MetricCard label={t.backtest.sharpeRatio} value={result.metrics.sharpe_ratio} />
                  <MetricCard label={t.backtest.winRate} value={result.metrics.win_rate} isPercent />
                  <MetricCard label={t.backtest.totalTrades} value={result.metrics.total_trades} />
                  <MetricCard label={t.backtest.profitFactor} value={result.metrics.profit_factor} />
                </div>
              </div>

              {/* Equity Curve */}
              <div className="bg-[var(--background)] border border-[var(--border-subtle)] rounded-lg p-4">
                <EquityCurve data={result.equity_curve} label={t.backtest.equityCurve} />
              </div>

              {/* Trade Log */}
              <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
                <h3 className="text-xs font-semibold mb-2 text-[var(--text-secondary)] uppercase tracking-wider">{t.backtest.tradeLog}</h3>
                {result.trades.length === 0 ? (
                  <p className="text-[var(--text-muted)] text-xs">{t.backtest.noResults}</p>
                ) : (
                  <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-[var(--text-muted)] text-[10px] uppercase tracking-wider bg-[var(--bg-secondary)]">
                          <th className="py-2 px-3 font-medium">{t.backtest.date}</th>
                          <th className="py-2 px-3 font-medium">{t.backtest.strategy}</th>
                          <th className="py-2 px-3 font-medium">{t.backtest.price}</th>
                          <th className="py-2 px-3 font-medium">{t.backtest.shares}</th>
                          <th className="py-2 px-3 font-medium">{t.backtest.reason}</th>
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
                              <td className="py-2 px-3 mono-nums text-[var(--text-secondary)]">{trade.date}</td>
                              <td className="py-2 px-3">
                                <span
                                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    isBuy
                                      ? "text-[var(--stock-down)] bg-[var(--stock-down-bg)]"
                                      : "text-[var(--stock-up)] bg-[var(--stock-up-bg)]"
                                  }`}
                                >
                                  {isBuy ? t.backtest.buy : t.backtest.sell}
                                </span>
                              </td>
                              <td className="py-2 px-3 mono-nums text-white">{formatNum(trade.price)}</td>
                              <td className="py-2 px-3 mono-nums text-[var(--text-secondary)]">{trade.shares.toLocaleString()}</td>
                              <td className="py-2 px-3 text-[var(--text-muted)]">{trade.reason}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
