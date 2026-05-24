"use client";

/**
 * Holdings Card List — Phase 7 mobile-first redesign.
 *
 * Mobile-friendly alternative to `holdings-table.tsx`. Same props
 * contract (`HoldingsTableProps`), but each position is rendered as a
 * vertical card — touch-friendly tap targets, no horizontal scroll, and
 * a deliberate visual hierarchy:
 *
 *   ┌────────────────────────────────────────────┐
 *   │ ☐  NVDA  [NASDAQ]                  $650.00 │  ← top: select + symbol + market + last_price
 *   │ Qty 100   Avg $580.00   Cost $58,000       │  ← mid: three stats
 *   │ P&L  +$7,000 (+12.07%)        Daily +$10   │  ← bottom: pnl + daily change
 *   └────────────────────────────────────────────┘
 *
 * Layout rationale:
 *   - Tapping the body fires `onRowClick`; the checkbox stops propagation
 *     so it never accidentally drills in.
 *   - Touch targets meet the 44 × 44 px iOS HIG minimum (checkbox cell is
 *     a full 44 × 44 hit-area; card padding is 14 × 16 with min-height 96).
 *   - P&L colour follows TW convention via `pnlColor()` (red = up).
 *   - Numerics use `tabular-nums` so vertically stacked figures align
 *     across cards.
 *   - Long symbols / accountless metadata simply wrap; we cap the symbol
 *     visually with `min-width: 0` + flex behaviour so the price never
 *     overruns the right edge.
 *
 * This file lives next to `holdings-table.tsx` and is composed by
 * `holdings-table-responsive.tsx` (CSS-only `hidden md:block` switch).
 */

import React, { useMemo, useState, useCallback, useRef, type ReactNode } from "react";
import { useSwipeable } from "react-swipeable";
import { GlassPanel } from "@/components/stratos/primitives";
import { MarketBadge } from "@/components/ui/badge";
import {
  type HoldingPosition,
  toNumber,
  fmt,
  fmtSigned,
  pnlColor,
} from "./types";

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

export interface HoldingsCardListProps {
  positions: HoldingPosition[];
  loading?: boolean;
  onRowClick?: (position: HoldingPosition) => void;
  selectedSymbols?: string[];
  onSelectionChange?: (symbols: string[]) => void;
  emptyState?: ReactNode;
  /**
   * Phase 8 R.1 — mobile swipe-left action.
   *
   * When provided, each card supports a swipe-left gesture that reveals
   * a red "Remove" affordance flush to the right edge. Tapping the
   * revealed button invokes this callback with the row's `symbol`.
   *
   * The card itself remains tappable (fires `onRowClick`); a small
   * deadzone (~40 px of horizontal travel) prevents accidental drills
   * during the gesture. When `undefined`, swipe wiring is skipped
   * entirely — no regression for callers that haven't adopted yet.
   *
   * Mobile-only is handled by the responsive wrapper
   * (`holdings-table-responsive.tsx`); this component itself doesn't
   * gate by viewport so it stays unit-testable in isolation.
   */
  onSwipeRemove?: (symbol: string) => void;
}

/* ------------------------------------------------------------------ */
/*  Derived row — same shape as the table's so future helpers stay     */
/*  drop-in compatible.                                                */
/* ------------------------------------------------------------------ */

interface DerivedRow {
  raw: HoldingPosition;
  qty: number;
  avg_cost: number | null;
  last_price: number | null;
  market_value: number | null;
  total_cost: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  daily_change: number | null;
  daily_change_pct: number | null;
}

function derive(p: HoldingPosition): DerivedRow {
  const qty = toNumber(p.qty) ?? 0;
  const last = toNumber(p.last_price);
  const marketValue = last != null ? qty * last : null;
  return {
    raw: p,
    qty,
    avg_cost: toNumber(p.avg_cost),
    last_price: last,
    market_value: marketValue,
    total_cost: toNumber(p.total_cost),
    unrealized_pnl: toNumber(p.unrealized_pnl),
    unrealized_pnl_pct: toNumber(p.unrealized_pnl_pct),
    daily_change: toNumber(p.daily_change),
    daily_change_pct: toNumber(p.daily_change_pct),
  };
}

/* ------------------------------------------------------------------ */
/*  Skeleton card                                                      */
/* ------------------------------------------------------------------ */

function SkeletonCard() {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--border-subtle)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        minHeight: 96,
      }}
    >
      <div
        style={{
          height: 14,
          background: "var(--card-hover)",
          width: "40%",
        }}
      />
      <div
        style={{
          height: 12,
          background: "var(--card-hover)",
          width: "80%",
        }}
      />
      <div
        style={{
          height: 12,
          background: "var(--card-hover)",
          width: "60%",
        }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Stat cell — label + value vertical pair                            */
/* ------------------------------------------------------------------ */

function Stat({
  label,
  value,
  color,
  align = "left",
}: {
  label: string;
  value: string;
  color?: string;
  align?: "left" | "right";
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 2,
        alignItems: align === "right" ? "flex-end" : "flex-start",
        minWidth: 0,
      }}
    >
      <span
        style={{
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--text-muted)",
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 13,
          fontWeight: 600,
          fontVariantNumeric: "tabular-nums",
          color: color ?? "var(--foreground)",
          whiteSpace: "nowrap",
        }}
      >
        {value}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Swipe-to-remove row wrapper — Phase 8 R.1                          */
/* ------------------------------------------------------------------ */

/**
 * Pixel threshold at which the swipe-left gesture "commits" — the row
 * snaps open to reveal the full action affordance. Anything shorter
 * springs back to closed. Tuned for ~80 px action width + a comfortable
 * margin so a hesitant flick is forgiving.
 */
const SWIPE_OPEN_THRESHOLD = 60;

/** Pixel width of the revealed "Remove" action. */
const ACTION_WIDTH = 88;

/**
 * Travel below which we still treat a release as a tap, not a drag.
 * Without this, the smallest pointer jitter would swallow the click.
 */
const TAP_DEADZONE = 6;

interface SwipeableCardRowProps {
  symbol: string;
  selected: boolean;
  onRemove: (symbol: string) => void;
  onTap?: () => void;
  children: ReactNode;
}

function SwipeableCardRow({
  symbol,
  selected,
  onRemove,
  onTap,
  children,
}: SwipeableCardRowProps) {
  // `offset` is the live drag-translate during the gesture; `open`
  // latches the row at -ACTION_WIDTH once the user commits.
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(false);
  // Tracks whether the last pointer interaction was a drag (vs a tap).
  // Updated synchronously by `onSwiping` so that the trailing `click`
  // event fired by the browser can be suppressed before it reaches
  // `onTap`. A ref (not state) so the value is read in the same tick
  // the click fires.
  const draggedRef = useRef(false);

  const handleSwiping = useCallback(
    (e: { deltaX: number; absX: number; absY: number }) => {
      // Ignore mostly-vertical gestures so users can still scroll the
      // page through the card. Tunable: absY > absX * 0.8 = scroll intent.
      if (e.absY > e.absX * 0.8) return;
      draggedRef.current = true;
      // Drag follows the finger leftwards, clamped to action width.
      // Open → starts from -ACTION_WIDTH so a swipe-right closes it.
      const base = open ? -ACTION_WIDTH : 0;
      const next = Math.min(0, Math.max(-ACTION_WIDTH, base + e.deltaX));
      setOffset(next);
    },
    [open],
  );

  const handleSwiped = useCallback(() => {
    if (offset <= -SWIPE_OPEN_THRESHOLD) {
      setOpen(true);
      setOffset(-ACTION_WIDTH);
    } else {
      setOpen(false);
      setOffset(0);
    }
  }, [offset]);

  const handlers = useSwipeable({
    onSwiping: handleSwiping,
    onSwiped: handleSwiped,
    // Allow mouse for desktop testing (chrome-devtools MCP / Playwright
    // emulation drives synthetic mouse events even in mobile mode).
    trackMouse: true,
    // Higher delta means a smaller initial jitter doesn't register —
    // critical so tap events still reach the inner button/checkbox.
    delta: TAP_DEADZONE,
    preventScrollOnSwipe: false,
  });

  // Single click handler — bubble phase. We bind it to the card body
  // wrapper so clicks on the inner checkbox label (which stops
  // propagation) never reach us. The row's `onTap` is called only for
  // genuine taps (no drag, not currently open, not on a child that
  // already handled the click).
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      const wasDragged = draggedRef.current;
      // Reset the drag flag for the next interaction. Doing it here
      // (rather than in onSwiped) guarantees we always clear, even on
      // gestures that bail out without a swiped event.
      draggedRef.current = false;
      // If the row is open, swallow the click and just close — the
      // user's intent is to dismiss the action drawer, not drill in.
      if (open) {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
        setOffset(0);
        return;
      }
      // If the last gesture was a drag, suppress the click so we don't
      // accidentally drill in after a horizontal swipe.
      if (wasDragged) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      // Genuine tap — delegate to the consumer.
      onTap?.();
    },
    [open, onTap],
  );

  return (
    <li
      style={{
        position: "relative",
        borderBottom: "1px solid var(--border-subtle)",
        background: selected ? "var(--card-active)" : "transparent",
        overflow: "hidden",
        // `touch-action: pan-y` keeps vertical scrolling smooth while
        // letting react-swipeable own horizontal pans.
        touchAction: "pan-y",
      }}
    >
      {/* Underlay: red "Remove" action, revealed as the row slides
        * left. Positioned absolutely so it doesn't affect the row's
        * layout when closed. */}
      <button
        type="button"
        aria-label={`Remove ${symbol}`}
        onClick={(e) => {
          e.stopPropagation();
          onRemove(symbol);
          setOpen(false);
          setOffset(0);
        }}
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          bottom: 0,
          width: ACTION_WIDTH,
          // Hard-coded red — `--stock-down` is green in the TW theme
          // (down = green per Asian market convention), but destructive
          // UI actions follow the universal red convention everywhere.
          background: "#dc2626",
          color: "white",
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          border: "none",
          cursor: "pointer",
          // Hide the button from AT when fully closed — it's purely
          // visual padding then.
          opacity: offset < 0 ? 1 : 0,
          transition: "opacity 0.12s",
          pointerEvents: offset < -TAP_DEADZONE ? "auto" : "none",
        }}
      >
        Remove
      </button>

      <div
        {...handlers}
        onClick={handleClick}
        style={{
          transform: `translateX(${offset}px)`,
          transition: offset === 0 || offset === -ACTION_WIDTH
            ? "transform 0.18s ease-out"
            : "none",
          // Preserve the row's selection tint via the slider so the
          // colour stays attached to the moving surface (not the
          // stationary `<li>` underneath).
          backgroundColor: selected ? "var(--card-active)" : "var(--background)",
          willChange: "transform",
        }}
      >
        {children}
      </div>
    </li>
  );
}

export function HoldingsCardList({
  positions,
  loading = false,
  onRowClick,
  selectedSymbols,
  onSelectionChange,
  emptyState,
  onSwipeRemove,
}: HoldingsCardListProps) {
  const selectedSet = useMemo(
    () => new Set(selectedSymbols ?? []),
    [selectedSymbols],
  );
  const selectionEnabled = !!onSelectionChange;

  const rows = useMemo(
    () =>
      // Mobile default: largest market_value first (matches table default).
      positions
        .map(derive)
        .sort(
          (a, b) =>
            (b.market_value ?? Number.NEGATIVE_INFINITY) -
            (a.market_value ?? Number.NEGATIVE_INFINITY),
        ),
    [positions],
  );

  const toggleOne = (symbol: string) => {
    if (!onSelectionChange) return;
    const next = new Set(selectedSet);
    if (next.has(symbol)) next.delete(symbol);
    else next.add(symbol);
    onSelectionChange(Array.from(next));
  };

  if (!loading && rows.length === 0) {
    return (
      <GlassPanel noPadding>
        <div
          style={{
            padding: 24,
            color: "var(--text-muted)",
            fontSize: 13,
            textAlign: "center",
          }}
        >
          {emptyState ?? "無持倉。點 + Add Trade 開始記錄。"}
        </div>
      </GlassPanel>
    );
  }

  /* ------------------------------------------------------------------ */
  /*  Render                                                              */
  /* ------------------------------------------------------------------ */

  return (
    <GlassPanel noPadding>
      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          color: "var(--foreground)",
        }}
      >
        {loading
          ? Array.from({ length: 5 }).map((_, i) => (
              <li key={i}>
                <SkeletonCard />
              </li>
            ))
          : rows.map((r) => {
              const sel = selectedSet.has(r.raw.symbol);
              const clickable = !!onRowClick;
              const swipeEnabled = !!onSwipeRemove;
              const rowKey = `${r.raw.account_id}-${r.raw.symbol}`;
              // The inner content tree is identical between swipe-on /
              // swipe-off — we just choose a different wrapper below.
              const cardBody = (
                  <div
                    role={clickable ? "button" : undefined}
                    tabIndex={clickable ? 0 : undefined}
                    onClick={swipeEnabled ? undefined : () => onRowClick?.(r.raw)}
                    onKeyDown={(e) => {
                      if (!clickable) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onRowClick?.(r.raw);
                      }
                    }}
                    style={{
                      padding: "14px 16px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 12,
                      cursor: clickable ? "pointer" : "default",
                      minHeight: 96,
                    }}
                  >
                    {/* Top row — checkbox + symbol + market badge + last price */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        minWidth: 0,
                      }}
                    >
                      {selectionEnabled && (
                        <label
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            // 44 × 44 hit-area per iOS HIG.
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            width: 44,
                            height: 44,
                            marginLeft: -10,
                            cursor: "pointer",
                            flexShrink: 0,
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={sel}
                            onChange={() => toggleOne(r.raw.symbol)}
                            style={{
                              accentColor: "var(--accent-cyan)",
                              cursor: "pointer",
                              width: 18,
                              height: 18,
                            }}
                          />
                        </label>
                      )}

                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          minWidth: 0,
                          flex: 1,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 15,
                            fontWeight: 700,
                            color: "var(--foreground)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            // Long Taiwanese ETF names truncate gracefully.
                            maxWidth: "100%",
                          }}
                          title={r.raw.symbol}
                        >
                          {r.raw.symbol}
                        </span>
                        <MarketBadge market={r.raw.market} />
                      </div>

                      <span
                        style={{
                          fontSize: 14,
                          fontWeight: 700,
                          fontVariantNumeric: "tabular-nums",
                          color: "var(--foreground)",
                          flexShrink: 0,
                        }}
                      >
                        {fmt(r.last_price, 2)}
                      </span>
                    </div>

                    {/* Middle row — Qty / Avg Cost / Total Cost */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr 1fr",
                        gap: 12,
                      }}
                    >
                      <Stat
                        label="Qty"
                        value={fmt(r.qty, r.qty % 1 === 0 ? 0 : 4)}
                      />
                      <Stat label="Avg" value={fmt(r.avg_cost, 2)} />
                      <Stat
                        label="Market Value"
                        value={fmt(r.market_value, 0)}
                        align="right"
                      />
                    </div>

                    {/* Bottom row — Unrealized P&L + Daily change */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "flex-end",
                        justifyContent: "space-between",
                        gap: 12,
                      }}
                    >
                      <Stat
                        label="損益"
                        value={
                          r.unrealized_pnl == null
                            ? "—"
                            : `${fmtSigned(r.unrealized_pnl, 0)}${
                                r.unrealized_pnl_pct == null
                                  ? ""
                                  : ` (${r.unrealized_pnl_pct >= 0 ? "+" : ""}${r.unrealized_pnl_pct.toFixed(2)}%)`
                              }`
                        }
                        color={pnlColor(r.unrealized_pnl)}
                      />
                      <Stat
                        label="今日"
                        value={
                          r.daily_change == null
                            ? "—"
                            : `${fmtSigned(r.daily_change, 0)}${
                                r.daily_change_pct == null
                                  ? ""
                                  : ` (${r.daily_change_pct >= 0 ? "+" : ""}${r.daily_change_pct.toFixed(2)}%)`
                              }`
                        }
                        color={pnlColor(r.daily_change)}
                        align="right"
                      />
                    </div>
                  </div>
              );

              if (swipeEnabled) {
                return (
                  <SwipeableCardRow
                    key={rowKey}
                    symbol={r.raw.symbol}
                    selected={sel}
                    onRemove={onSwipeRemove!}
                    onTap={clickable ? () => onRowClick?.(r.raw) : undefined}
                  >
                    {cardBody}
                  </SwipeableCardRow>
                );
              }

              return (
                <li
                  key={rowKey}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    background: sel ? "var(--card-active)" : "transparent",
                    transition: "background 0.12s",
                  }}
                >
                  {cardBody}
                </li>
              );
            })}
      </ul>
    </GlassPanel>
  );
}
