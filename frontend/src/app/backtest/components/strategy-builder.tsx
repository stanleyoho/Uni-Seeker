"use client";

import { useState, useEffect } from "react";
import { type StrategyInfo } from "@/lib/api-client";
import { useStrategies } from "@/hooks/use-backtest";
import { ParamGridBuilder, type ParamRange } from "./param-grid-builder";

/* ---------- Types ---------- */

export interface BacktestConfig {
  symbol: string;
  strategies: string[];
  compositeMode: "single" | "composite";
  compositeMerge: "ALL" | "MAJORITY" | "ANY";
  params: Record<string, unknown>;
  gridSearch: boolean;
  gridRanges: Record<string, ParamRange>;
  stopLoss?: number;
  takeProfit?: number;
  initialCapital: number;
  positionSize: number;
}

interface StrategyBuilderProps {
  onEnqueue: (config: BacktestConfig) => void;
  onRunNow: (config: BacktestConfig) => void;
}

/* ---------- Sub-components ---------- */

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
      className={`text-left p-3 rounded-lg border transition-all duration-200 w-full ${
        selected
          ? "bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30 animate-shimmer"
          : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] hover:bg-[var(--card-hover)]"
      }`}
    >
      <div className="font-medium text-[var(--foreground)] text-xs mb-0.5">
        {strategy.name}
      </div>
      <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
        {strategy.description}
      </div>
    </button>
  );
}

/* ---------- Main ---------- */

const inputClass =
  "w-full px-3 py-2 rounded-lg bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--foreground)] text-sm placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)]/30 transition-all duration-200";

export function StrategyBuilder({ onEnqueue, onRunNow }: StrategyBuilderProps) {
  const { data: strategies = [] } = useStrategies();

  // Form state
  const [symbol, setSymbol] = useState("");
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
  const [compositeMode, setCompositeMode] = useState<"single" | "composite">("single");
  const [compositeMerge, setCompositeMerge] = useState<"ALL" | "MAJORITY" | "ANY">("ALL");
  const [paramOverrides, setParamOverrides] = useState<Record<string, unknown>>({});
  const [gridSearch, setGridSearch] = useState(false);
  const [gridRanges, setGridRanges] = useState<Record<string, ParamRange>>({});
  const [stopLoss, setStopLoss] = useState<string>("");
  const [takeProfit, setTakeProfit] = useState<string>("");
  const [initialCapital, setInitialCapital] = useState(1_000_000);
  const [positionSize, setPositionSize] = useState(0.1);

  // Auto-select first strategy
  useEffect(() => {
    if (strategies.length > 0 && selectedStrategies.length === 0) {
      setSelectedStrategies([strategies[0].name]);
    }
  }, [strategies, selectedStrategies.length]);

  // Get current strategy params
  const currentStrategy = strategies.find(
    (s) => selectedStrategies.length === 1 && s.name === selectedStrategies[0]
  );
  const currentParams = currentStrategy?.params || {};

  const handleStrategyClick = (name: string) => {
    if (compositeMode === "single") {
      setSelectedStrategies([name]);
    } else {
      setSelectedStrategies((prev) =>
        prev.includes(name)
          ? prev.filter((s) => s !== name)
          : [...prev, name]
      );
    }
  };

  const handleParamChange = (key: string, value: string) => {
    const num = Number(value);
    setParamOverrides((prev) => ({
      ...prev,
      [key]: isNaN(num) ? value : num,
    }));
  };

  const buildConfig = (): BacktestConfig => ({
    symbol: symbol.trim().toUpperCase(),
    strategies: selectedStrategies,
    compositeMode,
    compositeMerge,
    params: paramOverrides,
    gridSearch,
    gridRanges,
    stopLoss: stopLoss ? Number(stopLoss) / 100 : undefined,
    takeProfit: takeProfit ? Number(takeProfit) / 100 : undefined,
    initialCapital,
    positionSize,
  });

  const isValid = symbol.trim() && selectedStrategies.length > 0;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Symbol */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1.5">
          股票代號
        </label>
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="e.g. 2330.TW, AAPL"
          className={inputClass}
        />
      </div>

      {/* Composite Mode Toggle */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-2">
          策略模式
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => {
              setCompositeMode("single");
              if (selectedStrategies.length > 1) {
                setSelectedStrategies([selectedStrategies[0]]);
              }
            }}
            className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200 border ${
              compositeMode === "single"
                ? "bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30 text-white"
                : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--card-hover)]"
            }`}
          >
            單一策略
          </button>
          <button
            onClick={() => setCompositeMode("composite")}
            className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200 border ${
              compositeMode === "composite"
                ? "bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30 text-white"
                : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--card-hover)]"
            }`}
          >
            複合策略
          </button>
        </div>

        {compositeMode === "composite" && (
          <div className="mt-3">
            <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-1.5">
              合併模式
            </label>
            <div className="flex gap-1.5">
              {(["ALL", "MAJORITY", "ANY"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setCompositeMerge(mode)}
                  className={`px-3 py-1.5 rounded-md text-[10px] font-medium transition-all duration-200 border ${
                    compositeMerge === mode
                      ? "bg-[var(--accent-blue)] text-white border-[var(--accent-blue)]"
                      : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-[var(--text-muted)] mt-1.5">
              {compositeMerge === "ALL" && "所有策略同時發出訊號才執行"}
              {compositeMerge === "MAJORITY" && "超過半數策略同意即執行"}
              {compositeMerge === "ANY" && "任一策略發出訊號即執行"}
            </p>
          </div>
        )}
      </div>

      {/* Strategy Picker */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-2">
          選擇策略{compositeMode === "composite" ? " (可多選)" : ""}
        </label>
        {strategies.length > 0 ? (
          <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            {strategies.map((s) => (
              <StrategyCard
                key={s.name}
                strategy={s}
                selected={selectedStrategies.includes(s.name)}
                onClick={() => handleStrategyClick(s.name)}
              />
            ))}
          </div>
        ) : (
          <div className="text-[var(--text-muted)] text-xs py-4 text-center">
            載入策略中...
          </div>
        )}
      </div>

      {/* Parameter Overrides / Grid Search */}
      {compositeMode === "single" && Object.keys(currentParams).length > 0 && (
        <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <label className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium">
              參數設定
            </label>
            <button
              onClick={() => setGridSearch(!gridSearch)}
              className={`px-2.5 py-1 rounded-md text-[10px] font-medium transition-all duration-200 border ${
                gridSearch
                  ? "bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/30 text-[var(--accent-blue)]"
                  : "bg-[var(--bg-secondary)] border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--foreground)]"
              }`}
            >
              Grid Search {gridSearch ? "ON" : "OFF"}
            </button>
          </div>

          {gridSearch ? (
            <ParamGridBuilder
              params={currentParams}
              onChange={setGridRanges}
            />
          ) : (
            <div className="space-y-2">
              {Object.entries(currentParams).map(([key, val]) => (
                <div key={key}>
                  <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
                    {key}{" "}
                    <span className="mono-nums text-[var(--text-muted)]">
                      (default: {String(val)})
                    </span>
                  </label>
                  <input
                    type="text"
                    placeholder={String(val)}
                    value={paramOverrides[key] !== undefined ? String(paramOverrides[key]) : ""}
                    onChange={(e) => handleParamChange(key, e.target.value)}
                    className={`${inputClass} mono-nums`}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Stop-Loss / Take-Profit */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-2">
          風險控制 (選填)
        </label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
              停損 (%)
            </label>
            <div className="relative">
              <input
                type="number"
                value={stopLoss}
                onChange={(e) => setStopLoss(e.target.value)}
                placeholder="e.g. 10"
                className={`${inputClass} mono-nums pr-8`}
                min={0}
                max={100}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] text-xs">
                %
              </span>
            </div>
          </div>
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
              停利 (%)
            </label>
            <div className="relative">
              <input
                type="number"
                value={takeProfit}
                onChange={(e) => setTakeProfit(e.target.value)}
                placeholder="e.g. 20"
                className={`${inputClass} mono-nums pr-8`}
                min={0}
                max={1000}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] text-xs">
                %
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Capital & Position */}
      <div className="bg-[var(--card-bg)] border border-[var(--border-subtle)] rounded-lg p-4">
        <label className="block text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium mb-2">
          資金配置
        </label>
        <div className="space-y-3">
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
              初始資金
            </label>
            <input
              type="number"
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value) || 0)}
              className={`${inputClass} mono-nums`}
            />
          </div>
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-0.5">
              部位比例:{" "}
              <span className="mono-nums">{(positionSize * 100).toFixed(0)}%</span>
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
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => isValid && onEnqueue(buildConfig())}
          disabled={!isValid}
          className="flex-1 py-2.5 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--text-secondary)] text-sm rounded-lg hover:bg-[var(--card-hover)] hover:text-[var(--foreground)] transition-all duration-200 disabled:opacity-40 font-medium"
        >
          加入佇列
        </button>
        <button
          onClick={() => isValid && onRunNow(buildConfig())}
          disabled={!isValid}
          className="flex-1 py-2.5 bg-[var(--accent-blue)] text-white text-sm rounded-lg hover:bg-[var(--accent-blue-hover)] transition-all duration-200 disabled:opacity-50 font-medium"
        >
          立即執行
        </button>
      </div>
    </div>
  );
}
