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
      <h3 className="text-lg font-semibold mb-3 text-white">{label}</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-3xl" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Grid */}
        {gridLines.map((g, i) => (
          <g key={i}>
            <line x1={PAD} y1={g.y} x2={W - PAD} y2={g.y} stroke="#1e293b" strokeWidth="1" />
            <text x={PAD - 4} y={g.y + 4} textAnchor="end" fill="#64748b" fontSize="10">
              {g.label}
            </text>
          </g>
        ))}
        {/* Gradient fill */}
        <path d={fillPath} fill="url(#equityGradient)" />
        {/* Line */}
        <polyline fill="none" stroke="#3b82f6" strokeWidth="2" points={points} />
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
  const colorClass = positive ? "text-green-400" : "text-red-400";
  const bgClass = positive ? "bg-green-500/5 border-green-500/10" : "bg-red-500/5 border-red-500/10";

  return (
    <div className={`rounded-xl p-4 border transition-all duration-200 hover:scale-[1.02] ${bgClass}`}>
      <p className="text-[#64748b] text-xs uppercase tracking-wider font-medium mb-1">{label}</p>
      <p className={`text-xl font-bold font-mono ${colorClass}`}>{display}</p>
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
      className={`text-left p-4 rounded-xl border transition-all duration-200 ${
        selected
          ? "bg-blue-600/10 border-blue-500/30 ring-1 ring-blue-500/20"
          : "bg-[#111827] border-[#1e293b] hover:border-[#253449] hover:bg-[#1e293b]"
      }`}
    >
      <div className="font-medium text-white text-sm mb-1">{strategy.name}</div>
      <div className="text-xs text-[#64748b] leading-relaxed">{strategy.description}</div>
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

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto animate-fade-in">
      <h1 className="text-3xl font-bold mb-6 text-white tracking-tight">{t.backtest.title}</h1>

      <div className="flex flex-col lg:flex-row gap-6 mb-6">
        {/* Configuration panel */}
        <div className="lg:w-[400px] lg:shrink-0">
          <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-5 sticky top-20">
            <div className="space-y-4">
              {/* Symbol */}
              <div>
                <label className="block text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">
                  {t.backtest.symbol}
                </label>
                <input
                  type="text"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  placeholder="e.g. 2330.TW, AAPL"
                  className="w-full px-3 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-white placeholder-[#64748b] focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200"
                />
              </div>

              {/* Strategy cards */}
              <div>
                <label className="block text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">
                  {t.backtest.strategy}
                </label>
                {strategies.length > 0 ? (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
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
                    className="w-full px-3 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-white focus:outline-none focus:border-blue-500 transition-all duration-200"
                  >
                    <option value="">--</option>
                  </select>
                )}
              </div>

              {/* Initial Capital */}
              <div>
                <label className="block text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">
                  {t.backtest.initialCapital}
                </label>
                <input
                  type="number"
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(Number(e.target.value) || 0)}
                  className="w-full px-3 py-2.5 rounded-xl bg-[#111827] border border-[#1e293b] text-white font-mono focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30 transition-all duration-200"
                />
              </div>

              {/* Position Size */}
              <div>
                <label className="block text-xs text-[#64748b] uppercase tracking-wider font-medium mb-1.5">
                  {t.backtest.positionSize}: {(positionSize * 100).toFixed(0)}%
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
                <div className="flex justify-between text-xs text-[#64748b] mt-1">
                  <span>10%</span>
                  <span>100%</span>
                </div>
              </div>
            </div>

            <button
              onClick={handleRun}
              disabled={loading || !symbol.trim() || !strategy}
              className="mt-5 w-full py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-all duration-200 disabled:opacity-50 font-medium shadow-lg shadow-blue-600/20"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {t.backtest.running}
                </span>
              ) : (
                t.backtest.run
              )}
            </button>

            {error && (
              <div className="mt-3 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}
          </div>
        </div>

        {/* Results panel */}
        <div className="flex-1 min-w-0">
          {!result && !loading && (
            <div className="flex items-center justify-center h-full min-h-[400px]">
              <div className="text-center">
                <svg className="w-16 h-16 mx-auto text-[#1e293b] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <p className="text-[#64748b]">{t.backtest.noResults}</p>
              </div>
            </div>
          )}

          {result && (
            <div className="space-y-6 animate-fade-in">
              {/* Metrics */}
              <div>
                <h2 className="text-lg font-semibold mb-3 text-white">{t.backtest.metrics}</h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
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
              <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-5">
                <EquityCurve data={result.equity_curve} label={t.backtest.equityCurve} />
              </div>

              {/* Trade Log */}
              <div className="bg-[#1a2332] border border-[#1e293b] rounded-2xl p-5">
                <h3 className="text-lg font-semibold mb-3 text-white">{t.backtest.tradeLog}</h3>
                {result.trades.length === 0 ? (
                  <p className="text-[#64748b]">{t.backtest.noResults}</p>
                ) : (
                  <div className="overflow-x-auto rounded-xl border border-[#1e293b]">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-[#64748b] text-xs uppercase tracking-wider bg-[#111827]">
                          <th className="py-3 px-4 font-medium">{t.backtest.date}</th>
                          <th className="py-3 px-4 font-medium">{t.backtest.strategy}</th>
                          <th className="py-3 px-4 font-medium">{t.backtest.price}</th>
                          <th className="py-3 px-4 font-medium">{t.backtest.shares}</th>
                          <th className="py-3 px-4 font-medium">{t.backtest.reason}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trades.map((trade, i) => {
                          const isBuy = trade.action.toUpperCase() === "BUY";
                          return (
                            <tr
                              key={i}
                              className={`border-t border-[#1e293b] transition-all duration-150 hover:bg-[#1e293b] ${
                                i % 2 === 0 ? "bg-[#1a2332]" : "bg-[#111827]/50"
                              }`}
                            >
                              <td className="py-3 px-4 font-mono text-[#94a3b8]">{trade.date}</td>
                              <td className="py-3 px-4">
                                <span
                                  className={`inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold tracking-wide ${
                                    isBuy
                                      ? "bg-green-500/10 text-green-400 border border-green-500/20"
                                      : "bg-red-500/10 text-red-400 border border-red-500/20"
                                  }`}
                                >
                                  {isBuy ? t.backtest.buy : t.backtest.sell}
                                </span>
                              </td>
                              <td className="py-3 px-4 font-mono text-white">{formatNum(trade.price)}</td>
                              <td className="py-3 px-4 font-mono text-[#94a3b8]">{trade.shares.toLocaleString()}</td>
                              <td className="py-3 px-4 text-[#64748b]">{trade.reason}</td>
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
