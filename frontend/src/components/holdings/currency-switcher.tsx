"use client";

/**
 * CurrencySwitcher — base-currency picker for the /holdings KPI row.
 *
 * STRATOS treatment:
 *   - Segmented control of the 7 supported ISO 4217 codes (TWD / USD /
 *     JPY / HKD / EUR / GBP / CNY). Selected pill uses --accent-cyan;
 *     unselected pills are --text-muted on transparent.
 *   - When `multiCurrencyAvailable === false` (Free/Basic tier),
 *     non-default pills render in a disabled state with an upsell
 *     tooltip on hover. The user can still click their account's
 *     native currency without restriction.
 *   - The component is purely controlled — the parent owns
 *     `selectedCurrency` and the persistence/auth strategy. We do not
 *     read localStorage or auth context here; that keeps the component
 *     trivially testable.
 *
 * A11y:
 *   - Renders as a `role="radiogroup"` with each pill as `role="radio"`
 *     so screen readers announce the single-selection semantics.
 *   - Disabled pills get `aria-disabled="true"` (NOT the native disabled
 *     attribute on the button — we still want hover-tooltip activation
 *     for the upsell hint).
 *   - Keyboard: arrow keys move focus + selection between enabled pills.
 *     Enter / Space selects.
 */

import React, { useCallback, useRef } from "react";
import {
  SUPPORTED_CURRENCIES,
  type Currency,
} from "@/lib/api-client";

export interface CurrencySwitcherProps {
  selectedCurrency: Currency;
  onSelect: (currency: Currency) => void;
  /**
   * When false (Free / Basic tier), selecting a non-default currency
   * is blocked at this layer — disabled pills surface the upsell
   * tooltip but do NOT fire `onSelect`. The page may still listen via
   * `onUpsellAttempt` to surface a modal.
   */
  multiCurrencyAvailable: boolean;
  loading?: boolean;
  /**
   * Optional callback fired when a tier-gated user clicks a disabled
   * pill. The page can open an upsell modal in response.
   */
  onUpsellAttempt?: (attemptedCurrency: Currency) => void;
  /**
   * The user's "home" / account currency — the one pill that stays
   * enabled even on Free / Basic. Defaults to TWD when unknown.
   */
  baseCurrencyForTier?: Currency;
  /** i18n hint copy; falls back to a hard-coded zh-TW string. */
  upgradeHint?: string;
  /** i18n title copy; falls back to "基準幣別". */
  title?: string;
}

const currencySymbol: Record<Currency, string> = {
  TWD: "NT$",
  USD: "$",
  JPY: "¥",
  HKD: "HK$",
  EUR: "€",
  GBP: "£",
  CNY: "¥",
};

/* ------------------------------------------------------------------ */
/*  Pill                                                               */
/* ------------------------------------------------------------------ */

interface PillProps {
  currency: Currency;
  active: boolean;
  disabled: boolean;
  upgradeHint: string;
  onClick: () => void;
  onUpsellAttempt: () => void;
  /** Index inside the radiogroup; used by arrow-key handler. */
  index: number;
  registerRef: (idx: number, el: HTMLButtonElement | null) => void;
  onArrowNav: (fromIdx: number, dir: 1 | -1) => void;
}

const basePillStyle: React.CSSProperties = {
  position: "relative",
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "6px 12px",
  background: "transparent",
  border: "1px solid var(--border-color)",
  fontFamily: "inherit",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  transition: "color 0.12s, background 0.12s, border-color 0.12s",
  fontVariantNumeric: "tabular-nums",
};

function Pill({
  currency,
  active,
  disabled,
  upgradeHint,
  onClick,
  onUpsellAttempt,
  index,
  registerRef,
  onArrowNav,
}: PillProps) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      onArrowNav(index, 1);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      onArrowNav(index, -1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (disabled) onUpsellAttempt();
      else onClick();
    }
  };

  return (
    <button
      ref={(el) => registerRef(index, el)}
      type="button"
      role="radio"
      aria-checked={active}
      aria-disabled={disabled || undefined}
      aria-label={
        disabled
          ? `${currency} — ${upgradeHint}`
          : currency
      }
      title={disabled ? upgradeHint : undefined}
      tabIndex={active ? 0 : -1}
      onClick={() => {
        if (disabled) onUpsellAttempt();
        else onClick();
      }}
      onKeyDown={handleKeyDown}
      style={{
        ...basePillStyle,
        color: active
          ? "var(--accent-cyan)"
          : disabled
            ? "var(--text-muted)"
            : "var(--foreground)",
        background: active ? "var(--card-hover)" : "transparent",
        borderColor: active
          ? "var(--accent-cyan)"
          : "var(--border-color)",
        opacity: disabled ? 0.4 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
      }}
      onMouseEnter={(e) => {
        if (!active && !disabled)
          e.currentTarget.style.background = "var(--card-hover)";
      }}
      onMouseLeave={(e) => {
        if (!active && !disabled)
          e.currentTarget.style.background = "transparent";
      }}
    >
      <span style={{ opacity: 0.6, fontSize: 10 }}>
        {currencySymbol[currency]}
      </span>
      <span>{currency}</span>
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Main                                                               */
/* ------------------------------------------------------------------ */

const wrapperStyle: React.CSSProperties = {
  background: "var(--glass-bg)",
  backdropFilter: "var(--glass-blur)",
  WebkitBackdropFilter: "var(--glass-blur)",
  border: "1px solid var(--border-color)",
  backgroundImage: "var(--glass-gradient)",
  boxShadow: "var(--glass-shadow)",
  borderRadius: "var(--glass-radius, 0)",
  padding: "10px 14px",
  display: "flex",
  alignItems: "center",
  gap: 12,
  flexWrap: "wrap",
};

export function CurrencySwitcher({
  selectedCurrency,
  onSelect,
  multiCurrencyAvailable,
  loading = false,
  onUpsellAttempt,
  baseCurrencyForTier = "TWD",
  upgradeHint = "升級 Pro 解鎖多幣別 portfolio",
  title = "基準幣別",
}: CurrencySwitcherProps) {
  // Keep refs to every pill button so the arrow-key navigator can
  // refocus across the radiogroup. We store them in a fixed-size array
  // indexed by the supported-currencies order.
  const refsRef = useRef<(HTMLButtonElement | null)[]>(
    new Array(SUPPORTED_CURRENCIES.length).fill(null),
  );

  const registerRef = useCallback(
    (idx: number, el: HTMLButtonElement | null) => {
      refsRef.current[idx] = el;
    },
    [],
  );

  const onArrowNav = useCallback(
    (fromIdx: number, dir: 1 | -1) => {
      // Skip past disabled pills so keyboard nav lands on a usable
      // target — matches the WAI-ARIA radiogroup pattern.
      const total = SUPPORTED_CURRENCIES.length;
      for (let step = 1; step <= total; step++) {
        const nextIdx = (fromIdx + dir * step + total) % total;
        const ccy = SUPPORTED_CURRENCIES[nextIdx];
        const isDisabled =
          !multiCurrencyAvailable && ccy !== baseCurrencyForTier;
        if (!isDisabled) {
          const target = refsRef.current[nextIdx];
          if (target) {
            target.focus();
            onSelect(ccy);
          }
          return;
        }
      }
    },
    [multiCurrencyAvailable, baseCurrencyForTier, onSelect],
  );

  if (loading) {
    return (
      <div style={wrapperStyle} aria-busy="true">
        <div
          style={{
            width: 80,
            height: 14,
            background: "var(--card-hover)",
          }}
        />
        <div
          style={{
            display: "flex",
            gap: 6,
          }}
        >
          {SUPPORTED_CURRENCIES.map((c) => (
            <div
              key={c}
              style={{
                width: 60,
                height: 28,
                background: "var(--card-hover)",
              }}
            />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={wrapperStyle}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--text-secondary)",
        }}
      >
        {title}
      </div>
      <div
        role="radiogroup"
        aria-label={title}
        style={{
          display: "flex",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        {SUPPORTED_CURRENCIES.map((ccy, idx) => {
          const isActive = ccy === selectedCurrency;
          // Tier gate: non-Pro users can only pick their home currency.
          // The "current selection" pill stays enabled so the user can
          // still see what's selected (e.g. when an admin downgraded
          // them after they had picked USD).
          const isDisabled =
            !multiCurrencyAvailable &&
            ccy !== baseCurrencyForTier &&
            ccy !== selectedCurrency;
          return (
            <Pill
              key={ccy}
              currency={ccy}
              active={isActive}
              disabled={isDisabled}
              upgradeHint={upgradeHint}
              index={idx}
              registerRef={registerRef}
              onArrowNav={onArrowNav}
              onClick={() => onSelect(ccy)}
              onUpsellAttempt={() => onUpsellAttempt?.(ccy)}
            />
          );
        })}
      </div>
      {!multiCurrencyAvailable && (
        <div
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            marginLeft: "auto",
          }}
        >
          {upgradeHint}
        </div>
      )}
    </div>
  );
}

// Re-export the currency symbol table — KPI row uses it to prefix
// totals with a glyph that matches the selected base.
export const CURRENCY_SYMBOL = currencySymbol;
