"use client";

/**
 * 四大買賣點 (Best Four Buy/Sell Points) — TW-only scanner card.
 *
 * Read-only view of the daily server-side scan (the backend computes the
 * full TW universe post-close and caches it; this card just reads
 * `GET /scanner/best-four-point`). Two columns: 買進訊號 / 賣出訊號, each row
 * showing symbol, name, verdict, the triggered reasons, and last close.
 *
 * STRATOS styling: GlassPanel shell, var(--stock-up)/var(--stock-down) for
 * the buy/sell accents, tabular-nums for prices.
 */

import { GlassPanel } from "@/components/stratos/primitives";
import { LoadingSpinner } from "@/components/ui/loading";
import { getErrorMessage } from "@/lib/type-guards";
import { useBestFourPoint } from "@/hooks/use-scanner";
import type { BestFourPointRow } from "@/lib/api-client";

function SignalRow({ row, side }: { row: BestFourPointRow; side: "buy" | "sell" }) {
  const reasons = side === "buy" ? row.buy_points ?? [] : row.sell_points ?? [];
  const accent = side === "buy" ? "var(--stock-up)" : "var(--stock-down)";
  // Decimal-as-string convention: coerce with Number() before display.
  const close =
    row.last_close != null && Number.isFinite(Number(row.last_close))
      ? Number(row.last_close).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      : "—";

  return (
    <li
      className="flex items-start gap-3 border-b border-[var(--border-subtle)] last:border-b-0 py-2.5"
      data-testid={`b4p-${side}-row`}
    >
      <a
        href={`/stocks/${encodeURIComponent(row.symbol)}`}
        className="shrink-0 w-[88px]"
      >
        <div className="text-sm font-bold tabular-nums text-[var(--foreground)] hover:text-[var(--accent-cyan)] transition-colors">
          {row.symbol}
        </div>
        <div className="text-[10px] text-[var(--text-muted)] truncate">{row.name}</div>
      </a>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap gap-1">
          {reasons.map((reason) => (
            <span
              key={reason}
              className="inline-block px-1.5 py-0.5 text-[10px] font-bold rounded border"
              style={{ color: accent, borderColor: accent }}
            >
              {reason}
            </span>
          ))}
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-sm font-bold tabular-nums" style={{ color: accent }}>
          {row.verdict}
        </div>
        <div className="text-[10px] text-[var(--text-muted)] tabular-nums">{close}</div>
      </div>
    </li>
  );
}

function SignalColumn({
  title,
  rows,
  side,
  emptyLabel,
}: {
  title: string;
  rows: BestFourPointRow[];
  side: "buy" | "sell";
  emptyLabel: string;
}) {
  const accent = side === "buy" ? "var(--stock-up)" : "var(--stock-down)";
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2 px-1">
        <h3 className="text-sm font-bold uppercase tracking-tighter" style={{ color: accent }}>
          {title}
        </h3>
        <span className="text-[10px] font-bold text-[var(--text-muted)] tabular-nums uppercase tracking-widest">
          {rows.length} 檔
        </span>
      </div>
      <GlassPanel noPadding>
        {rows.length === 0 ? (
          <p className="py-8 text-center text-[11px] font-bold uppercase tracking-widest text-[var(--text-muted)]">
            {emptyLabel}
          </p>
        ) : (
          <ul className="flex flex-col px-3">
            {rows.map((row) => (
              <SignalRow key={row.symbol} row={row} side={side} />
            ))}
          </ul>
        )}
      </GlassPanel>
    </div>
  );
}

export function BestFourPointCard() {
  const { data, isLoading, error } = useBestFourPoint();

  return (
    <div className="space-y-4" data-testid="best-four-point-card">
      <div className="flex items-end justify-between border-b border-[var(--border-subtle)] pb-3">
        <div>
          <h2 className="text-2xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
            四大買賣點
          </h2>
          <p className="text-[11px] font-bold text-[var(--text-muted)] tracking-widest mt-0.5 uppercase">
            Best Four Points · 台股盤後掃描
          </p>
        </div>
        {data?.scan_date && (
          <span className="text-[11px] font-bold text-[var(--text-muted)] tabular-nums uppercase tracking-widest">
            掃描日 {data.scan_date} · 共 {data.total_scanned ?? 0} 檔
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="py-16 flex justify-center">
          <LoadingSpinner />
        </div>
      ) : error ? (
        <GlassPanel className="py-16 text-center">
          <p className="text-red-400 font-bold">ERROR: {getErrorMessage(error).toUpperCase()}</p>
        </GlassPanel>
      ) : !data?.scan_date ? (
        <GlassPanel className="py-16 text-center">
          <p className="text-[var(--text-muted)] font-bold uppercase tracking-widest text-xs">
            尚無掃描資料（每日盤後計算）
          </p>
        </GlassPanel>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SignalColumn
            title="四大買點"
            side="buy"
            rows={data.buy_signals ?? []}
            emptyLabel="今日無買進訊號"
          />
          <SignalColumn
            title="四大賣點"
            side="sell"
            rows={data.sell_signals ?? []}
            emptyLabel="今日無賣出訊號"
          />
        </div>
      )}
    </div>
  );
}
