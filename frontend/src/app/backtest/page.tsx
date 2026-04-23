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

  // Grid lines (4 horizontal)
  const gridLines = Array.from({ length: 5 }, (_, i) => {
    const y = PAD + (i / 4) * (H - PAD * 2);
    const val = max - (i / 4) * range;
    return { y, label: formatMoney(val) };
  });

  return (
    <div className="w-full overflow-x-auto">
      <h3 className="text-lg font-semibold mb-2">{label}</h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-3xl" preserveAspectRatio="xMidYMid meet">
        {/* Grid */}
        {gridLines.map((g, i) => (
          <g key={i}>
            <line x1={PAD} y1={g.y} x2={W - PAD} y2={g.y} stroke="#374151" strokeWidth="1" />
            <text x={PAD - 4} y={g.y + 4} textAnchor="end" fill="#9CA3AF" fontSize="10">
              {g.label}
            </text>
          </g>
        ))}
        {/* Line */}
        <polyline fill="none" stroke="#34D399" strokeWidth="2" points={points} />
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
  const color = positive ? "text-green-400" : "text-red-400";

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <p className="text-gray-400 text-sm mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{display}</p>
    </div>
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
        setError(t("backtest.insufficientData"));
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t("backtest.title")}</h1>

      {/* Configuration form */}
      <div className="bg-gray-800 rounded-lg p-4 mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Symbol */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t("backtest.symbol")}</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="e.g. 2330.TW, AAPL"
              className="w-full px-3 py-2 rounded-lg bg-gray-700 border border-gray-600 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Strategy */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t("backtest.strategy")}</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-gray-700 border border-gray-600 text-white focus:outline-none focus:border-blue-500"
            >
              {strategies.length === 0 && <option value="">--</option>}
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name} — {s.description}
                </option>
              ))}
            </select>
          </div>

          {/* Initial Capital */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">{t("backtest.initialCapital")}</label>
            <input
              type="number"
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value) || 0)}
              className="w-full px-3 py-2 rounded-lg bg-gray-700 border border-gray-600 text-white focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Position Size */}
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              {t("backtest.positionSize")}: {(positionSize * 100).toFixed(0)}%
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
          </div>
        </div>

        <button
          onClick={handleRun}
          disabled={loading || !symbol.trim() || !strategy}
          className="mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
        >
          {loading ? t("backtest.running") : t("backtest.run")}
        </button>

        {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
      </div>

      {/* Results */}
      {!result && !loading && (
        <p className="text-gray-500 text-center py-12">{t("backtest.noResults")}</p>
      )}

      {result && (
        <>
          {/* Metrics */}
          <h2 className="text-lg font-semibold mb-3">{t("backtest.metrics")}</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <MetricCard label={t("backtest.totalReturn")} value={result.metrics.total_return} isPercent />
            <MetricCard label={t("backtest.annualizedReturn")} value={result.metrics.annualized_return} isPercent />
            <MetricCard label={t("backtest.maxDrawdown")} value={result.metrics.max_drawdown} isPercent invertColor />
            <MetricCard label={t("backtest.sharpeRatio")} value={result.metrics.sharpe_ratio} />
            <MetricCard label={t("backtest.winRate")} value={result.metrics.win_rate} isPercent />
            <MetricCard label={t("backtest.totalTrades")} value={result.metrics.total_trades} />
            <MetricCard label={t("backtest.profitFactor")} value={result.metrics.profit_factor} />
          </div>

          {/* Equity Curve */}
          <div className="bg-gray-800 rounded-lg p-4 mb-6">
            <EquityCurve data={result.equity_curve} label={t("backtest.equityCurve")} />
          </div>

          {/* Trade Log */}
          <div className="bg-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold mb-3">{t("backtest.tradeLog")}</h3>
            {result.trades.length === 0 ? (
              <p className="text-gray-500">{t("backtest.noResults")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-400 border-b border-gray-700">
                      <th className="py-2 pr-4">{t("backtest.date")}</th>
                      <th className="py-2 pr-4">{t("backtest.strategy")}</th>
                      <th className="py-2 pr-4">{t("backtest.price")}</th>
                      <th className="py-2 pr-4">{t("backtest.shares")}</th>
                      <th className="py-2">{t("backtest.reason")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((trade, i) => {
                      const isBuy = trade.action.toUpperCase() === "BUY";
                      return (
                        <tr key={i} className="border-b border-gray-700/50">
                          <td className="py-2 pr-4 font-mono text-gray-300">{trade.date}</td>
                          <td className="py-2 pr-4">
                            <span
                              className={`px-2 py-0.5 rounded text-xs font-semibold ${
                                isBuy
                                  ? "bg-green-900/50 text-green-400"
                                  : "bg-red-900/50 text-red-400"
                              }`}
                            >
                              {isBuy ? t("backtest.buy") : t("backtest.sell")}
                            </span>
                          </td>
                          <td className="py-2 pr-4 font-mono">{formatNum(trade.price)}</td>
                          <td className="py-2 pr-4 font-mono">{trade.shares.toLocaleString()}</td>
                          <td className="py-2 text-gray-400">{trade.reason}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
