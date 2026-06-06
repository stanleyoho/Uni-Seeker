"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  GlassPanel,
  ClippedButton,
  KpiCard,
} from "@/components/stratos/primitives";
import { AmbientBackground } from "@/components/stratos/ambient";
import { useRunBacktest, useStrategies } from "@/hooks/use-backtest";
import {
  runAutoDiscovery,
  type AutoDiscoveryResponse,
  type AutoDiscoveryPhaseRow,
  type BacktestResult,
} from "@/lib/api-client";
import { getErrorMessage } from "@/lib/type-guards";
import { LoadingSpinner } from "@/components/ui/loading";
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
/*  Shared input styling                                               */
/* ------------------------------------------------------------------ */

const inputCls =
  "w-full px-4 py-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm font-bold text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none transition-all tabular-nums";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-2 block";

/* ------------------------------------------------------------------ */
/*  BacktestResults — reused from original (manual mode)               */
/* ------------------------------------------------------------------ */

/* CI for a single metric (backend Decimal-as-string -> Number). */
type MetricCI = { median: string; ci_low: string; ci_high: string };

/**
 * Render a "[low, high]" 90% confidence-interval caption for a KPI's `delta`
 * slot. `digits` matches the metric's own precision; `suffix` appends a unit
 * (e.g. "%"). Falls back to a plain label when no CI was estimated (small
 * samples -> backend sends null).
 */
function ciCaption(
  ci: MetricCI | null | undefined,
  digits: number,
  suffix = "",
): string {
  if (!ci) return "Performance Metric";
  const low = Number(ci.ci_low).toFixed(digits);
  const high = Number(ci.ci_high).toFixed(digits);
  return `90% CI [${low}${suffix}, ${high}${suffix}]`;
}

function BacktestResults({ results }: { results: BacktestResult }) {
  const m = results.metrics;
  if (!m) return null;

  // Backend ships Decimal-as-string for all metric fields -- coerce once.
  const totalReturn = Number(m.total_return);
  const maxDrawdown = Number(m.max_drawdown);
  const sharpe = Number(m.sharpe_ratio);
  const winRate = Number(m.win_rate);
  const profitFactor = Number(m.profit_factor);

  // Bootstrap confidence intervals (null when sample too small to estimate).
  const bs = results.bootstrap;

  const kpiData: {
    label: string;
    value: string;
    delta: string;
    direction: "up" | "down" | "flat";
  }[] = [
    {
      label: "Total Return",
      value: `${totalReturn.toFixed(2)}%`,
      // CI is on annualized return (CAGR), the bootstrappable analogue of
      // the total return shown above.
      delta: bs?.annualized_return
        ? `CAGR 90% CI [${Number(bs.annualized_return.ci_low).toFixed(2)}%, ${Number(bs.annualized_return.ci_high).toFixed(2)}%]`
        : "Performance Metric",
      direction: totalReturn > 0 ? "up" : "down",
    },
    {
      label: "Max Drawdown",
      value: `${maxDrawdown.toFixed(2)}%`,
      delta: ciCaption(bs?.max_drawdown, 2, "%"),
      direction: "down",
    },
    {
      label: "Sharpe Ratio",
      value: sharpe.toFixed(2),
      delta: ciCaption(bs?.sharpe_ratio, 2),
      direction: sharpe > 1 ? "up" : "flat",
    },
    {
      label: "Win Rate",
      value: `${winRate.toFixed(1)}%`,
      delta: ciCaption(bs?.win_rate, 1, "%"),
      direction: winRate > 50 ? "up" : "down",
    },
  ];

  const chartData = (results.equity_curve || []).map((val, i) => ({
    day: i,
    equity: Math.round(Number(val)),
  }));

  return (
    <GlassPanel title="BACKTESTING SIMULATION RESULTS">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {kpiData.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      {/* Trade summary */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-[var(--bg-secondary)] p-4 border border-[var(--border-subtle)]">
          <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
            TOTAL TRADES
          </p>
          <p className="text-2xl font-bold text-[var(--foreground)] tabular-nums mt-1">
            {m.total_trades}
          </p>
        </div>
        <div className="bg-[var(--bg-secondary)] p-4 border border-[var(--border-subtle)]">
          <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
            PROFIT FACTOR
          </p>
          <p className="text-2xl font-bold text-[var(--foreground)] tabular-nums mt-1">
            {profitFactor.toFixed(2)}
          </p>
        </div>
        <div className="bg-[var(--bg-secondary)] p-4 border border-[var(--border-subtle)]">
          <p className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
            STRATEGY
          </p>
          <p className="text-lg font-bold text-[var(--accent-cyan)] mt-1 uppercase">
            {results.strategy}
          </p>
        </div>
      </div>

      <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-4">
        EQUITY CURVE
      </h4>
      <div className="h-[400px] w-full bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-4">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 5, right: 20, left: -10, bottom: 5 }}
          >
            <defs>
              <linearGradient
                id="equityGradient"
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="5%"
                  stopColor="var(--accent-cyan)"
                  stopOpacity={0.4}
                />
                <stop
                  offset="95%"
                  stopColor="var(--accent-cyan)"
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid
              stroke="var(--border-subtle)"
              strokeDasharray="3 3"
            />
            <XAxis
              dataKey="day"
              stroke="var(--text-muted)"
              tick={{ fontSize: 10 }}
            />
            <YAxis
              stroke="var(--text-muted)"
              tick={{ fontSize: 10 }}
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}K`}
            />
            <Tooltip
              contentStyle={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                fontSize: "12px",
              }}
              labelStyle={{ color: "var(--foreground)", fontWeight: "bold" }}
              formatter={(value: unknown) => [
                `$${Number(value).toLocaleString()}`,
                "Equity",
              ]}
            />
            <Area
              type="monotone"
              dataKey="equity"
              stroke="var(--accent-cyan)"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#equityGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Trade log */}
      {results.trades && results.trades.length > 0 && (
        <>
          <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-4 mt-8">
            TRADE LOG ({results.trades.length} EXECUTIONS)
          </h4>
          <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[var(--bg-secondary)]">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th className="text-left py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                    DATE
                  </th>
                  <th className="text-left py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                    ACTION
                  </th>
                  <th className="text-right py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                    PRICE
                  </th>
                  <th className="text-right py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                    SHARES
                  </th>
                  <th className="text-left py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                    REASON
                  </th>
                </tr>
              </thead>
              <tbody>
                {results.trades.map((t, i) => (
                  <tr
                    key={i}
                    className="border-b border-[var(--border-subtle)] hover:bg-[var(--card-hover)]"
                  >
                    <td className="py-1.5 px-3 font-mono text-xs">
                      {t.date}
                    </td>
                    <td className="py-1.5 px-3">
                      <span
                        className={`text-xs font-bold ${t.action === "BUY" ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}
                      >
                        {t.action}
                      </span>
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono text-xs tabular-nums">
                      {Number(t.price).toFixed(2)}
                    </td>
                    <td className="py-1.5 px-3 text-right font-mono text-xs tabular-nums">
                      {t.shares}
                    </td>
                    <td className="py-1.5 px-3 text-xs text-[var(--text-muted)] truncate max-w-[200px]">
                      {t.reason}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  AutoDiscoveryResults                                               */
/* ------------------------------------------------------------------ */

function AutoDiscoveryResults({ data }: { data: AutoDiscoveryResponse | null }) {
  if (!data) return null;

  const best = data.best_overall;
  const buyHold = data.buy_and_hold;
  const phase1 = data.phase1_results || [];
  const phase2 = data.phase2_results || [];
  const phase3 = data.phase3_results || [];

  const outperform =
    best && buyHold
      ? ((best.total_return ?? 0) - (buyHold.total_return ?? 0)).toFixed(1)
      : null;

  return (
    <div className="space-y-6">
      {/* Best Overall */}
      {best && (
        <GlassPanel>
          <div className="border-l-4 border-[var(--accent-cyan)] pl-6">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-2xl">&#x1f3c6;</span>
              <div>
                <h3 className="text-lg font-bold text-[var(--foreground)] uppercase">
                  BEST OVERALL
                </h3>
                <p className="text-sm font-bold text-[var(--accent-cyan)] uppercase">
                  {best.strategy_name || best.strategy || "N/A"}
                  {best.strategy_params &&
                    Object.keys(best.strategy_params).length > 0 &&
                    ` (${Object.entries(best.strategy_params)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")})`}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className={labelCls}>RETURN</p>
                <p
                  className={`text-xl font-bold tabular-nums ${(best.total_return ?? 0) >= 0 ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}
                >
                  {(best.total_return ?? 0) >= 0 ? "+" : ""}
                  {(best.total_return ?? 0).toFixed(2)}%
                </p>
              </div>
              <div>
                <p className={labelCls}>SHARPE</p>
                <p className="text-xl font-bold text-[var(--foreground)] tabular-nums">
                  {(best.sharpe_ratio ?? 0).toFixed(2)}
                </p>
              </div>
              <div>
                <p className={labelCls}>WIN RATE</p>
                <p className="text-xl font-bold text-[var(--foreground)] tabular-nums">
                  {(best.win_rate ?? 0).toFixed(1)}%
                </p>
              </div>
              <div>
                <p className={labelCls}>MAX DRAWDOWN</p>
                <p className="text-xl font-bold text-[var(--stock-down)] tabular-nums">
                  {(best.max_drawdown ?? 0).toFixed(2)}%
                </p>
              </div>
            </div>
            {buyHold && outperform && (
              <div className="mt-4 pt-4 border-t border-[var(--border-subtle)]">
                <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest">
                  VS BUY &amp; HOLD:{" "}
                  <span className="text-[var(--foreground)]">
                    {(buyHold.total_return ?? 0).toFixed(1)}%
                  </span>
                  <span
                    className={`ml-2 ${Number(outperform) >= 0 ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}
                  >
                    ({Number(outperform) >= 0 ? "OUTPERFORM" : "UNDERPERFORM"}{" "}
                    {Number(outperform) >= 0 ? "+" : ""}
                    {outperform}%)
                  </span>
                </p>
              </div>
            )}
          </div>
        </GlassPanel>
      )}

      {/* Phase tables */}
      <PhaseTable
        title="PHASE 1: SINGLE STRATEGY SCAN"
        rows={phase1}
        phaseNum={1}
      />
      <PhaseTable
        title="PHASE 2: PARAMETER OPTIMIZATION"
        rows={phase2}
        phaseNum={2}
      />
      <PhaseTable
        title="PHASE 3: COMPOSITE STRATEGY"
        rows={phase3}
        phaseNum={3}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PhaseTable                                                         */
/* ------------------------------------------------------------------ */

function PhaseTable({
  title,
  rows,
  phaseNum,
}: {
  title: string;
  rows: AutoDiscoveryPhaseRow[];
  phaseNum: number;
}) {
  if (!rows || rows.length === 0) return null;

  const accentColors: Record<number, string> = {
    1: "var(--accent-cyan)",
    2: "var(--accent-gold, #f0b90b)",
    3: "var(--stock-up, #00c853)",
  };
  const accent = accentColors[phaseNum] || "var(--accent-cyan)";

  return (
    <GlassPanel title={title}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)]">
              <th className="text-left py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                #
              </th>
              <th className="text-left py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                STRATEGY
              </th>
              <th className="text-right py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                RETURN
              </th>
              <th className="text-right py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                SHARPE
              </th>
              <th className="text-right py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                WIN %
              </th>
              <th className="text-right py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                TRADES
              </th>
              <th className="text-right py-2 px-3 text-[10px] font-bold uppercase text-[var(--text-muted)]">
                DRAWDOWN
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const name =
                r.strategy_name || r.strategy || r.name || "Unknown";
              const params = r.strategy_params || r.params || {};
              const paramStr =
                Object.keys(params).length > 0
                  ? ` (${Object.entries(params)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")})`
                  : "";
              return (
                <tr
                  key={i}
                  className="border-b border-[var(--border-subtle)] hover:bg-[var(--card-hover)] transition-colors"
                >
                  <td className="py-2 px-3 font-mono text-xs tabular-nums">
                    <span
                      style={{ color: i === 0 ? accent : "var(--text-muted)" }}
                      className="font-bold"
                    >
                      {i + 1}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-xs font-bold uppercase text-[var(--foreground)]">
                    {name}
                    <span className="font-normal text-[var(--text-muted)]">
                      {paramStr}
                    </span>
                  </td>
                  <td
                    className={`py-2 px-3 text-right font-mono text-xs font-bold tabular-nums ${(r.total_return ?? 0) >= 0 ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}
                  >
                    {(r.total_return ?? 0) >= 0 ? "+" : ""}
                    {(r.total_return ?? 0).toFixed(2)}%
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-xs tabular-nums">
                    {(r.sharpe_ratio ?? 0).toFixed(2)}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-xs tabular-nums">
                    {(r.win_rate ?? 0).toFixed(1)}%
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-xs tabular-nums">
                    {r.total_trades ?? 0}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-xs tabular-nums text-[var(--stock-down)]">
                    {(r.max_drawdown ?? 0).toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  Discovery Progress                                                 */
/* ------------------------------------------------------------------ */

function DiscoveryProgress() {
  const [dots, setDots] = useState("");

  useEffect(() => {
    const iv = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "" : d + "."));
    }, 500);
    return () => clearInterval(iv);
  }, []);

  const phases = [
    { label: "PHASE 1", desc: "SINGLE STRATEGY SCAN" },
    { label: "PHASE 2", desc: "PARAMETER OPTIMIZATION" },
    { label: "PHASE 3", desc: "COMPOSITE STRATEGY SEARCH" },
  ];

  return (
    <GlassPanel className="py-12">
      <div className="flex flex-col items-center gap-6">
        <LoadingSpinner />
        <p className="text-sm font-bold text-[var(--accent-cyan)] uppercase tracking-[0.2em]">
          AUTO DISCOVERY ENGINE RUNNING{dots}
        </p>
        <div className="w-full max-w-md space-y-3 mt-4">
          {phases.map((p, i) => (
            <div
              key={i}
              className="flex items-center gap-3 px-4 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)]"
            >
              <div className="w-2 h-2 rounded-full bg-[var(--accent-cyan)] animate-pulse" />
              <span className="text-[10px] font-bold text-[var(--accent-cyan)] tracking-widest">
                {p.label}
              </span>
              <span className="text-[10px] font-bold text-[var(--text-muted)] tracking-widest">
                {p.desc}
              </span>
            </div>
          ))}
        </div>
      </div>
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  Mode Toggle                                                        */
/* ------------------------------------------------------------------ */

function ModeToggle({
  mode,
  onModeChange,
}: {
  mode: "auto" | "manual";
  onModeChange: (m: "auto" | "manual") => void;
}) {
  return (
    <div className="flex">
      <button
        onClick={() => onModeChange("auto")}
        className={`px-6 py-3 text-xs font-bold uppercase tracking-[0.15em] border transition-all ${
          mode === "auto"
            ? "bg-[var(--accent-cyan)] text-black border-[var(--accent-cyan)]"
            : "bg-transparent text-[var(--text-muted)] border-[var(--border-subtle)] hover:text-[var(--foreground)] hover:border-[var(--foreground)]"
        }`}
      >
        AUTO DISCOVERY
      </button>
      <button
        onClick={() => onModeChange("manual")}
        className={`px-6 py-3 text-xs font-bold uppercase tracking-[0.15em] border border-l-0 transition-all ${
          mode === "manual"
            ? "bg-[var(--accent-cyan)] text-black border-[var(--accent-cyan)]"
            : "bg-transparent text-[var(--text-muted)] border-[var(--border-subtle)] hover:text-[var(--foreground)] hover:border-[var(--foreground)]"
        }`}
      >
        MANUAL STRATEGY
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function BacktestPage() {
  const [mode, setMode] = useState<"auto" | "manual">("auto");

  // Shared
  const [symbol, setSymbol] = useState("2330.TW");
  const [capital, setCapital] = useState("1000000");
  const [positionSize, setPositionSize] = useState("10");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  // Manual-specific
  const [strategyChoice, setStrategy] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");

  // Auto discovery state
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoResults, setAutoResults] = useState<AutoDiscoveryResponse | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);

  // Manual backtest
  const {
    mutate: runManual,
    data: manualResults,
    isPending: manualPending,
    error: manualError,
  } = useRunBacktest();

  // Strategies list
  const { data: strategies } = useStrategies();

  // Derived: user's pick or the first strategy in the loaded list. Avoids
  // a setState-in-effect bootstrap step (the upstream query already
  // re-renders us when `strategies` arrives).
  const strategy = strategyChoice || strategies?.[0]?.name || "";

  /* ---- handlers ---- */

  const handleAutoDiscovery = async () => {
    setAutoLoading(true);
    setAutoResults(null);
    setAutoError(null);
    try {
      const res = await runAutoDiscovery({
        symbol,
        initial_capital: Number(capital) || 1_000_000,
        position_size: (Number(positionSize) || 10) / 100,
        start_date: startDate || null,
        end_date: endDate || null,
      });
      setAutoResults(res);
    } catch (err: unknown) {
      setAutoError(getErrorMessage(err) || "Auto discovery failed");
    } finally {
      setAutoLoading(false);
    }
  };

  const handleManualBacktest = () => {
    runManual({
      symbol,
      strategy,
      params: {},
      initial_capital: Number(capital) || 1_000_000,
      position_size: (Number(positionSize) || 10) / 100,
      stop_loss: stopLoss ? Number(stopLoss) / 100 : null,
      take_profit: takeProfit ? Number(takeProfit) / 100 : null,
      start_date: startDate || null,
      end_date: endDate || null,
    });
  };

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in space-y-6">
        {/* Header with mode toggle */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <ModeToggle mode={mode} onModeChange={setMode} />
          <Link
            href="/portfolio/backtest/history"
            className="text-xs font-bold uppercase tracking-[0.15em] text-[var(--text-muted)] hover:text-[var(--accent-cyan)] transition-colors"
          >
            VIEW HISTORY &rarr;
          </Link>
        </div>

        {/* ============================================================ */}
        {/*  AUTO DISCOVERY MODE                                         */}
        {/* ============================================================ */}
        {mode === "auto" && (
          <>
            <GlassPanel title="AUTO DISCOVERY ENGINE">
              <div className="space-y-6">
                {/* Symbol */}
                <div>
                  <label className={labelCls}>SYMBOL</label>
                  <input
                    type="text"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    placeholder="e.g., AAPL, 2330.TW"
                    className={inputCls}
                  />
                </div>

                {/* Capital + Position */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelCls}>CAPITAL</label>
                    <input
                      type="text"
                      value={capital}
                      onChange={(e) => setCapital(e.target.value)}
                      placeholder="1,000,000"
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>POSITION SIZE (%)</label>
                    <input
                      type="text"
                      value={positionSize}
                      onChange={(e) => setPositionSize(e.target.value)}
                      placeholder="10"
                      className={inputCls}
                    />
                  </div>
                </div>

                {/* Date Range */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelCls}>START DATE (OPTIONAL)</label>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>END DATE (OPTIONAL)</label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className={inputCls}
                    />
                  </div>
                </div>

                {/* Launch button */}
                <ClippedButton
                  variant="red-solid"
                  size="lg"
                  className="w-full"
                  onClick={handleAutoDiscovery}
                  disabled={autoLoading || !symbol.trim()}
                >
                  {autoLoading
                    ? "DISCOVERY IN PROGRESS..."
                    : "LAUNCH DISCOVERY"}
                </ClippedButton>

                {/* Info box */}
                <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-4 space-y-1">
                  <p className="text-[10px] font-bold text-[var(--accent-cyan)] uppercase tracking-widest flex items-center gap-2">
                    <span className="text-base">&#x26A1;</span> TESTS ALL
                    STRATEGIES AUTOMATICALLY
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest pl-6">
                    PHASE 1: SINGLE STRATEGY SCAN
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest pl-6">
                    PHASE 2: PARAMETER OPTIMIZATION
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest pl-6">
                    PHASE 3: COMPOSITE STRATEGY SEARCH
                  </p>
                </div>
              </div>
            </GlassPanel>

            {/* Auto loading */}
            {autoLoading && <DiscoveryProgress />}

            {/* Auto error */}
            {autoError && (
              <GlassPanel className="py-12 text-center">
                <p className="text-red-400 font-bold mb-4 uppercase">
                  DISCOVERY FAILED: {autoError}
                </p>
                <ClippedButton
                  variant="red-ghost"
                  size="sm"
                  onClick={handleAutoDiscovery}
                >
                  RETRY
                </ClippedButton>
              </GlassPanel>
            )}

            {/* Auto results */}
            {autoResults && <AutoDiscoveryResults data={autoResults} />}
          </>
        )}

        {/* ============================================================ */}
        {/*  MANUAL STRATEGY MODE                                        */}
        {/* ============================================================ */}
        {mode === "manual" && (
          <>
            <GlassPanel title="MANUAL STRATEGY CONFIGURATION">
              <div className="space-y-6">
                {/* Symbol */}
                <div>
                  <label className={labelCls}>SYMBOL</label>
                  <input
                    type="text"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    placeholder="e.g., AAPL, 2330.TW"
                    className={inputCls}
                  />
                </div>

                {/* Strategy dropdown */}
                <div>
                  <label className={labelCls}>STRATEGY</label>
                  <select
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                    className={`${inputCls} cursor-pointer appearance-none`}
                    style={{
                      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%2388929e' viewBox='0 0 16 16'%3E%3Cpath d='M8 11L3 6h10z'/%3E%3C/svg%3E")`,
                      backgroundRepeat: "no-repeat",
                      backgroundPosition: "right 16px center",
                    }}
                  >
                    {strategies && strategies.length > 0 ? (
                      strategies.map((s) => (
                        <option key={s.name} value={s.name}>
                          {s.name.toUpperCase()} — {s.description}
                        </option>
                      ))
                    ) : (
                      <option value="">LOADING STRATEGIES...</option>
                    )}
                  </select>
                </div>

                {/* Capital + Position */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelCls}>CAPITAL</label>
                    <input
                      type="text"
                      value={capital}
                      onChange={(e) => setCapital(e.target.value)}
                      placeholder="1,000,000"
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>POSITION SIZE (%)</label>
                    <input
                      type="text"
                      value={positionSize}
                      onChange={(e) => setPositionSize(e.target.value)}
                      placeholder="10"
                      className={inputCls}
                    />
                  </div>
                </div>

                {/* Stop Loss + Take Profit */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelCls}>STOP LOSS (%)</label>
                    <input
                      type="text"
                      value={stopLoss}
                      onChange={(e) => setStopLoss(e.target.value)}
                      placeholder="OPTIONAL"
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>TAKE PROFIT (%)</label>
                    <input
                      type="text"
                      value={takeProfit}
                      onChange={(e) => setTakeProfit(e.target.value)}
                      placeholder="OPTIONAL"
                      className={inputCls}
                    />
                  </div>
                </div>

                {/* Date Range */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className={labelCls}>START DATE (OPTIONAL)</label>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>END DATE (OPTIONAL)</label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className={inputCls}
                    />
                  </div>
                </div>

                {/* Execute button */}
                <ClippedButton
                  variant="red-solid"
                  size="lg"
                  className="w-full"
                  onClick={handleManualBacktest}
                  disabled={manualPending || !symbol.trim() || !strategy}
                >
                  {manualPending
                    ? "RUNNING SIMULATION..."
                    : "EXECUTE BACKTEST"}
                </ClippedButton>
              </div>
            </GlassPanel>

            {/* Manual loading */}
            {manualPending && (
              <GlassPanel className="py-20 text-center">
                <LoadingSpinner />
                <p className="mt-4 text-sm font-bold text-[var(--text-muted)] uppercase tracking-widest">
                  PROCESSING HISTORICAL DATA...
                </p>
              </GlassPanel>
            )}

            {/* Manual error */}
            {manualError && (
              <GlassPanel className="py-12 text-center">
                <p className="text-red-400 font-bold mb-4 uppercase">
                  BACKTEST FAILED: {manualError.message.toUpperCase()}
                </p>
                <ClippedButton
                  variant="red-ghost"
                  size="sm"
                  onClick={handleManualBacktest}
                >
                  RETRY
                </ClippedButton>
              </GlassPanel>
            )}

            {/* Manual results */}
            {manualResults && <BacktestResults results={manualResults} />}
          </>
        )}
      </main>
    </div>
  );
}
