"use client";

import { useState, type ReactNode } from "react";
import {
  INDICATOR_DOCS,
  type IndicatorKey,
} from "../indicator-docs";

interface IndicatorCardProps {
  indicator: IndicatorKey;
  enabled: boolean;
  onToggle: (next: boolean) => void;
  children: ReactNode;
}

/**
 * Condition card for a single indicator (RSI / MACD / Bollinger / KD /
 * SMA Cross / Volume). Hosts:
 *   - enable checkbox
 *   - tooltip ℹ with plain-Chinese definition (from INDICATOR_DOCS)
 *   - threshold input slot (passed via `children`)
 *   - greyed-out "backend unavailable" state when no backend strategy
 *     is registered (KD / Volume today — see indicator-docs.ts)
 */
export function IndicatorCard({
  indicator,
  enabled,
  onToggle,
  children,
}: IndicatorCardProps) {
  const [showTip, setShowTip] = useState(false);
  const doc = INDICATOR_DOCS[indicator];
  const unavailable = doc.backendStrategyKey === null;

  return (
    <div
      className="relative p-3 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] transition-all"
      style={{
        clipPath:
          "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))",
        opacity: unavailable ? 0.55 : 1,
      }}
      data-testid={`indicator-card-${indicator}`}
    >
      <div className="flex items-center justify-between mb-2">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => onToggle(e.target.checked)}
            disabled={unavailable}
            className="w-3.5 h-3.5 accent-[var(--accent-cyan)] cursor-pointer disabled:cursor-not-allowed"
            aria-label={`Enable ${doc.label}`}
          />
          <span className="text-[12px] font-bold uppercase tracking-wider text-[var(--foreground)]">
            {doc.label}
          </span>
        </label>

        <button
          type="button"
          onClick={() => setShowTip((s) => !s)}
          onBlur={() => setShowTip(false)}
          onMouseEnter={() => setShowTip(true)}
          onMouseLeave={() => setShowTip(false)}
          aria-label={`${doc.label} 說明`}
          aria-expanded={showTip}
          className="w-5 h-5 rounded-full border border-[var(--border-subtle)] text-[10px] font-bold text-[var(--text-muted)] hover:text-[var(--accent-cyan)] hover:border-[var(--accent-cyan)] transition-colors flex items-center justify-center"
        >
          i
        </button>
      </div>

      {showTip && (
        <div
          role="tooltip"
          className="absolute z-20 right-2 top-9 max-w-[260px] p-2.5 text-[11px] leading-relaxed bg-[var(--background)] border border-[var(--accent-cyan)]/40 text-[var(--text-secondary)] shadow-lg"
        >
          {doc.description}
        </div>
      )}

      <div className={`mt-1 ${enabled && !unavailable ? "" : "opacity-60"}`}>
        {children}
      </div>

      {unavailable && (
        <p className="mt-2 text-[10px] font-bold uppercase tracking-wider text-[var(--stock-up)]/80">
          Backend strategy unavailable
        </p>
      )}
    </div>
  );
}
