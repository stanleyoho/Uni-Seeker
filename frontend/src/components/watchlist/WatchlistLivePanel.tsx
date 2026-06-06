"use client";

/**
 * WatchlistLivePanel — live-updating indicator panel for the watchlist.
 *
 * A2 "Stock.Indicators streaming hub" (scoped v1). Renders, per watched
 * symbol, the live price + a few key indicators (RSI, MA cross state, %
 * distance from the long MA), auto-refreshing on a poll interval via
 * `useWatchlistIndicators`.
 *
 * Why a panel separate from `WatchlistRail`: the rail is a dense single-line
 * navigation list (symbol → name → price). This panel surfaces the *analytic*
 * dimension (indicators) and lives wherever there's room for a wider card
 * (e.g. the /watchlist page). It deliberately reuses the same data hook and
 * styling tokens so the two stay visually coherent.
 *
 * Conventions:
 *   - Taiwan 紅漲綠跌 via `pnlColor` (positive → --stock-up red, negative →
 *     --stock-down green). The MA-cross badge follows the same direction:
 *     golden cross = up colour, death cross = down colour.
 *   - Decimal-as-string: every numeric field arrives as a string; we call
 *     Number() before comparing/formatting and render null/NaN as an em-dash.
 *   - Freshness: each successful poll bumps `dataUpdatedAt`; we briefly flash
 *     a "live" dot so the user can see the panel is updating without reading
 *     a timestamp. `aria-live="polite"` announces refreshes to AT users.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useWatchlistIndicators } from "@/hooks/use-watchlist-indicators";
import { pnlColor } from "@/components/holdings/types";
import type { WatchlistLiveIndicator } from "@/lib/api-client";

const DASH = "—";

export interface WatchlistLivePanelProps {
  /** Symbols to track (typically the user's current watchlist). */
  symbols: string[];
  /** Optional poll cadence override (ms). */
  refetchIntervalMs?: number;
  /** Optional className escape hatch. */
  className?: string;
}

function toNum(v: string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Strip TW market suffixes for display while keeping the original for routing. */
function displaySymbol(symbol: string): string {
  return symbol.replace(/\.TW$|\.TWO$/, "");
}

/** Format a signed fixed-2 number, or em-dash when missing. */
function fmtSigned(n: number | null, suffix = ""): string {
  if (n === null) return DASH;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}${suffix}`;
}

function fmtPrice(n: number | null): string {
  if (n === null) return DASH;
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** RSI colour band: overbought (>=70) red, oversold (<=30) green, else muted. */
function rsiColor(rsi: number | null): string {
  if (rsi === null) return "var(--text-muted)";
  if (rsi >= 70) return "var(--stock-up)";
  if (rsi <= 30) return "var(--stock-down)";
  return "var(--text-secondary)";
}

const CROSS_LABEL: Record<string, string> = {
  golden: "黃金交叉",
  death: "死亡交叉",
  flat: "持平",
};

function MaCrossBadge({ cross }: { cross: string | null | undefined }) {
  if (!cross) return <span style={{ color: "var(--text-muted)" }}>{DASH}</span>;
  // golden = bullish (up colour), death = bearish (down colour).
  const color =
    cross === "golden"
      ? "var(--stock-up)"
      : cross === "death"
        ? "var(--stock-down)"
        : "var(--text-secondary)";
  return (
    <span
      className="text-[10px] font-semibold px-1.5 py-0.5 rounded tabular-nums"
      style={{ color, border: `1px solid ${color}`, opacity: 0.95 }}
    >
      {CROSS_LABEL[cross] ?? cross}
    </span>
  );
}

/**
 * One row of the panel. Memo-free (the list is short — a watchlist); the
 * parent re-renders cheaply on each poll.
 */
function LiveRow({ item }: { item: WatchlistLiveIndicator }) {
  const price = toNum(item.last_price);
  const change = toNum(item.change);
  const changePct = toNum(item.change_percent);
  const rsi = toNum(item.rsi);
  const pctFromMa = toNum(item.pct_from_ma_long);
  const sym = displaySymbol(item.symbol);

  return (
    <Link
      href={`/stocks/${encodeURIComponent(item.symbol)}`}
      className="grid items-center gap-2 px-3 py-2 hover:bg-[var(--card-hover)] transition-colors border-b border-[var(--border-color)] last:border-b-0"
      style={{ gridTemplateColumns: "1.1fr 1fr 0.7fr 0.9fr 0.8fr" }}
      data-testid={`watchlist-live-row-${item.symbol}`}
    >
      {/* Symbol */}
      <span className="font-bold text-[13px] text-[var(--foreground)] tabular-nums truncate">
        {sym}
      </span>

      {/* Price + change% */}
      <span className="flex flex-col items-end text-right tabular-nums">
        <span className="text-[13px] text-[var(--foreground)] font-semibold">
          {fmtPrice(price)}
        </span>
        <span
          className="text-[10px] font-semibold"
          style={{ color: pnlColor(changePct) }}
        >
          {fmtSigned(change)} ({fmtSigned(changePct, "%")})
        </span>
      </span>

      {/* RSI */}
      <span
        className="text-[12px] font-semibold tabular-nums text-right"
        style={{ color: rsiColor(rsi) }}
        title="RSI(14)"
      >
        {rsi === null ? DASH : rsi.toFixed(1)}
      </span>

      {/* MA cross */}
      <span className="flex justify-end">
        <MaCrossBadge cross={item.ma_cross} />
      </span>

      {/* % from long MA */}
      <span
        className="text-[12px] font-semibold tabular-nums text-right"
        style={{ color: pnlColor(pctFromMa) }}
        title="距 MA20 %"
      >
        {fmtSigned(pctFromMa, "%")}
      </span>
    </Link>
  );
}

/** Brief "live" pulse that flashes whenever a fresh poll lands. */
function FreshnessDot({ updatedAt }: { updatedAt: number }) {
  const [flash, setFlash] = useState(false);
  const prev = useRef(updatedAt);

  useEffect(() => {
    if (updatedAt !== prev.current) {
      prev.current = updatedAt;
      setFlash(true);
      const id = setTimeout(() => setFlash(false), 600);
      return () => clearTimeout(id);
    }
  }, [updatedAt]);

  return (
    <span
      aria-hidden="true"
      data-testid="watchlist-live-dot"
      data-flash={flash ? "true" : "false"}
      className="inline-block rounded-full transition-opacity"
      style={{
        width: 6,
        height: 6,
        background: "var(--accent-cyan)",
        opacity: flash ? 1 : 0.35,
        boxShadow: flash ? "0 0 6px var(--accent-cyan)" : "none",
      }}
    />
  );
}

export function WatchlistLivePanel({
  symbols,
  refetchIntervalMs,
  className,
}: WatchlistLivePanelProps) {
  const { data, isLoading, isError, dataUpdatedAt } = useWatchlistIndicators(
    symbols,
    refetchIntervalMs !== undefined ? { refetchIntervalMs } : {},
  );

  const items = data ?? [];

  return (
    <section
      data-testid="watchlist-live-panel"
      aria-label="自選股即時指標"
      className={[
        "flex flex-col rounded-lg overflow-hidden",
        "border border-[var(--border-color)]",
        className ?? "",
      ].join(" ")}
      style={{
        background: "var(--glass-bg, rgba(255,255,255,0.02))",
        backgroundImage: "var(--glass-gradient)",
        backdropFilter: "var(--glass-blur)",
        WebkitBackdropFilter: "var(--glass-blur)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 border-b"
        style={{ borderColor: "var(--border-color)" }}
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            style={{
              width: 3,
              height: 12,
              background: "var(--accent-cyan)",
              borderRadius: 1,
            }}
          />
          <span
            className="text-[11px] font-bold uppercase tracking-[0.12em]"
            style={{ color: "var(--accent-cyan)" }}
          >
            即時指標
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <FreshnessDot updatedAt={dataUpdatedAt} />
          <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
            自動更新
          </span>
        </div>
      </div>

      {/* Column headers */}
      <div
        className="grid items-center gap-2 px-3 py-1.5 text-[10px] uppercase tracking-wider"
        style={{
          gridTemplateColumns: "1.1fr 1fr 0.7fr 0.9fr 0.8fr",
          color: "var(--text-muted)",
          borderBottom: "1px solid var(--border-color)",
        }}
      >
        <span>代號</span>
        <span className="text-right">價格 / 漲跌</span>
        <span className="text-right">RSI</span>
        <span className="text-right">均線</span>
        <span className="text-right">距MA20</span>
      </div>

      {/* Body */}
      <div
        className="flex flex-col"
        aria-live="polite"
        aria-busy={isLoading ? "true" : "false"}
      >
        {isError ? (
          <p
            data-testid="watchlist-live-error"
            className="px-3 py-4 text-[12px]"
            style={{ color: "var(--stock-down)" }}
          >
            指標載入失敗，稍後將自動重試。
          </p>
        ) : symbols.length === 0 ? (
          <p
            data-testid="watchlist-live-empty"
            className="px-3 py-4 text-[12px]"
            style={{ color: "var(--text-secondary)" }}
          >
            尚未追蹤任何標的。
          </p>
        ) : isLoading && items.length === 0 ? (
          <p
            data-testid="watchlist-live-skeleton"
            className="px-3 py-4 text-[12px]"
            style={{ color: "var(--text-muted)" }}
          >
            載入中...
          </p>
        ) : (
          items.map((item) => <LiveRow key={item.symbol} item={item} />)
        )}
      </div>
    </section>
  );
}

export default WatchlistLivePanel;
