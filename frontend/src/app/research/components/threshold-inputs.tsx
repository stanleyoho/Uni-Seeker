"use client";

import type {
  BollingerParams,
  KdParams,
  MacdParams,
  RsiParams,
  SmaCrossParams,
  VolumeParams,
} from "../templates";

// Shared input style — matches the rest of the STRATOS form surfaces.
const inputCls =
  "w-20 px-2 py-1 text-xs font-mono font-bold tabular-nums bg-[var(--background)] border border-[var(--border-subtle)] text-[var(--foreground)] focus:border-[var(--accent-cyan)] focus:outline-none transition-colors";
const selectCls =
  "px-2 py-1 text-xs font-bold uppercase bg-[var(--background)] border border-[var(--border-subtle)] text-[var(--foreground)] focus:border-[var(--accent-cyan)] focus:outline-none transition-colors";
const rowCls = "flex items-center gap-2 text-[11px] text-[var(--text-secondary)]";

export function RsiInputs({
  value,
  onChange,
  disabled,
}: {
  value: RsiParams;
  onChange: (next: RsiParams) => void;
  disabled?: boolean;
}) {
  return (
    <div className={rowCls}>
      <span>RSI</span>
      <select
        className={selectCls}
        value={value.op}
        onChange={(e) => onChange({ ...value, op: e.target.value as RsiParams["op"] })}
        disabled={disabled}
        aria-label="RSI operator"
      >
        <option value="<">{"<"}</option>
        <option value=">">{">"}</option>
      </select>
      <input
        type="number"
        min={0}
        max={100}
        step={1}
        className={inputCls}
        value={value.value}
        onChange={(e) => onChange({ ...value, value: Number(e.target.value) || 0 })}
        disabled={disabled}
        aria-label="RSI threshold"
      />
    </div>
  );
}

export function MacdInputs({
  value,
  onChange,
  disabled,
}: {
  value: MacdParams;
  onChange: (next: MacdParams) => void;
  disabled?: boolean;
}) {
  return (
    <div className={rowCls}>
      <span>Signal</span>
      <select
        className={selectCls}
        value={value.signal}
        onChange={(e) => onChange({ signal: e.target.value as MacdParams["signal"] })}
        disabled={disabled}
        aria-label="MACD signal direction"
      >
        <option value="bullish_cross">黃金交叉</option>
        <option value="bearish_cross">死亡交叉</option>
      </select>
    </div>
  );
}

export function BollingerInputs({
  value,
  onChange,
  disabled,
}: {
  value: BollingerParams;
  onChange: (next: BollingerParams) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className={rowCls}>
        <span>通道寬度 ≤</span>
        <input
          type="number"
          min={0}
          max={100}
          step={0.5}
          className={inputCls}
          value={value.widthPct}
          onChange={(e) => onChange({ ...value, widthPct: Number(e.target.value) || 0 })}
          disabled={disabled}
          aria-label="Bollinger width percent"
        />
        <span>%</span>
      </div>
      <div className={rowCls}>
        <span>突破</span>
        <select
          className={selectCls}
          value={value.breakout}
          onChange={(e) =>
            onChange({ ...value, breakout: e.target.value as BollingerParams["breakout"] })
          }
          disabled={disabled}
          aria-label="Bollinger breakout direction"
        >
          <option value="upper">上軌</option>
          <option value="lower">下軌</option>
        </select>
      </div>
    </div>
  );
}

export function KdInputs({
  value,
  onChange,
  disabled,
}: {
  value: KdParams;
  onChange: (next: KdParams) => void;
  disabled?: boolean;
}) {
  return (
    <div className={rowCls}>
      <span>K</span>
      <select
        className={selectCls}
        value={value.op}
        onChange={(e) => onChange({ ...value, op: e.target.value as KdParams["op"] })}
        disabled={disabled}
        aria-label="KD operator"
      >
        <option value="<">{"<"}</option>
        <option value=">">{">"}</option>
      </select>
      <input
        type="number"
        min={0}
        max={100}
        step={1}
        className={inputCls}
        value={value.level}
        onChange={(e) => onChange({ ...value, level: Number(e.target.value) || 0 })}
        disabled={disabled}
        aria-label="KD level"
      />
    </div>
  );
}

export function SmaCrossInputs({
  value,
  onChange,
  disabled,
}: {
  value: SmaCrossParams;
  onChange: (next: SmaCrossParams) => void;
  disabled?: boolean;
}) {
  return (
    <div className={rowCls}>
      <span>短</span>
      <input
        type="number"
        min={1}
        max={250}
        step={1}
        className={inputCls}
        value={value.shortPeriod}
        onChange={(e) => onChange({ ...value, shortPeriod: Number(e.target.value) || 1 })}
        disabled={disabled}
        aria-label="SMA short period"
      />
      <span>長</span>
      <input
        type="number"
        min={2}
        max={400}
        step={1}
        className={inputCls}
        value={value.longPeriod}
        onChange={(e) => onChange({ ...value, longPeriod: Number(e.target.value) || 2 })}
        disabled={disabled}
        aria-label="SMA long period"
      />
    </div>
  );
}

export function VolumeInputs({
  value,
  onChange,
  disabled,
}: {
  value: VolumeParams;
  onChange: (next: VolumeParams) => void;
  disabled?: boolean;
}) {
  return (
    <div className={rowCls}>
      <span>量 ≥ 20 日均量 ×</span>
      <input
        type="number"
        min={0}
        step={0.1}
        className={inputCls}
        value={value.multipleOf20dAvg}
        onChange={(e) =>
          onChange({ multipleOf20dAvg: Number(e.target.value) || 0 })
        }
        disabled={disabled}
        aria-label="Volume multiple of 20-day average"
      />
    </div>
  );
}
