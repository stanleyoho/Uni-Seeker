"use client";

/**
 * WatchlistRail — sticky right-side watchlist panel.
 *
 * Per Stanley's home polish brief (the "missing 90%-of-finance-apps pattern"
 * — Yahoo Dock / eToro / Koyfin / Robinhood all ship a persistent right rail).
 *
 * Behaviour:
 *   - Visible only on `≥lg` viewports. Smaller breakpoints have a dedicated
 *     `/watchlist` page (and the existing Watchlist panel inside Portfolio),
 *     so the rail just disappears below `lg`.
 *   - Sticky pinning is owned by the root layout (the layout mounts the rail
 *     in a flex column to the right of the main content). The rail itself
 *     constrains its height to `calc(100vh - <header + ticker>)` and scrolls
 *     internally so it never overruns the page footer.
 *   - Authenticated: list rows from `useWatchlistApi` rendered through the
 *     canonical `QuoteRow` (compact variant — single line per row, fits a
 *     ~240px panel width).
 *   - Unauthenticated: a "登入後追蹤" CTA card linking to /login.
 *   - Empty (authenticated, zero items): a hint pointing the user to add
 *     stocks via the stock detail page.
 *
 * Drag-reorder is intentionally out of scope for this PR.
 */

import Link from "next/link";
import { useAuth } from "@/contexts/auth-context";
import { useWatchlistApi } from "@/hooks/use-watchlist-api";
import { QuoteRow } from "@/components/quote-row";
import { useI18n } from "@/i18n/context";
import type { WatchlistItem } from "@/lib/api-client";

/**
 * Header height (64px) + TickerStrip height (40px) = 104px reserved at the
 * top of the viewport by layout.tsx. The rail must constrain itself to the
 * remaining vertical room so it never pushes the page footer.
 */
const RAIL_OFFSET_PX = 104;

export interface WatchlistRailProps {
  /** Optional className escape hatch (mostly for tests). */
  className?: string;
}

export function WatchlistRail({ className }: WatchlistRailProps) {
  const { user, loading: authLoading } = useAuth();
  const { data: items = [], isLoading: itemsLoading } = useWatchlistApi();
  const { t } = useI18n();

  // The aria-label gives the landmark a distinct name from the main page
  // heading, so screen-reader users can skip past or jump to the rail.
  const watchlistLabel =
    (t.watchlist && (t.watchlist as { title?: string }).title) ?? "Watchlist";

  return (
    <aside
      data-testid="watchlist-rail"
      aria-label={watchlistLabel}
      className={[
        // Hidden on <lg per spec; on lg+ becomes a fixed-width column.
        "hidden lg:flex flex-col shrink-0",
        // Sticky to the top of the scroll container; the height clamp keeps
        // the rail inside the viewport without overshooting the footer.
        "sticky top-0 self-start",
        "border-l border-[var(--border-color)]",
        className ?? "",
      ].join(" ")}
      style={{
        width: 240,
        height: `calc(100vh - ${RAIL_OFFSET_PX}px)`,
        background: "var(--glass-bg, rgba(255,255,255,0.02))",
        backgroundImage: "var(--glass-gradient)",
        backdropFilter: "var(--glass-blur)",
        WebkitBackdropFilter: "var(--glass-blur)",
      }}
    >
      {/* Header strip — matches the home page's accent-bar section label. */}
      <div
        className="flex items-center justify-between px-3 py-2 shrink-0 border-b"
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
            {watchlistLabel}
          </span>
        </div>
        {user && items.length > 0 && (
          <span
            className="text-[10px] tabular-nums"
            style={{ color: "var(--text-muted)" }}
          >
            {items.length}
          </span>
        )}
      </div>

      {/* Scrollable body — only this region scrolls; sticky frame stays put. */}
      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
        <WatchlistRailBody
          authLoading={authLoading}
          isAuthed={!!user}
          itemsLoading={itemsLoading}
          items={items}
        />
      </div>
    </aside>
  );
}

interface WatchlistRailBodyProps {
  authLoading: boolean;
  isAuthed: boolean;
  itemsLoading: boolean;
  items: WatchlistItem[];
}

/**
 * Body branches: auth-loading → skeleton, unauth → login CTA, empty → hint,
 * has items → list of QuoteRow (compact). Extracted so the state machine
 * sits in one place and the surrounding chrome stays simple.
 */
function WatchlistRailBody({
  authLoading,
  isAuthed,
  itemsLoading,
  items,
}: WatchlistRailBodyProps) {
  if (authLoading) {
    return (
      <div
        data-testid="watchlist-rail-skeleton"
        className="px-3 py-4 text-[11px]"
        style={{ color: "var(--text-muted)" }}
      >
        ...
      </div>
    );
  }

  if (!isAuthed) {
    return (
      <div
        data-testid="watchlist-rail-cta"
        className="flex flex-col items-stretch gap-2 px-3 py-4"
      >
        <p
          className="text-[12px] leading-snug"
          style={{ color: "var(--text-secondary)" }}
        >
          登入後追蹤你的自選股
        </p>
        <Link
          href="/login"
          className="text-center text-[11px] font-semibold uppercase tracking-[0.08em] px-3 py-2 rounded"
          style={{
            background: "var(--accent-primary)",
            color: "white",
          }}
        >
          登入 / 註冊
        </Link>
      </div>
    );
  }

  if (itemsLoading) {
    return (
      <div
        data-testid="watchlist-rail-skeleton"
        className="px-3 py-4 text-[11px]"
        style={{ color: "var(--text-muted)" }}
      >
        載入中...
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div
        data-testid="watchlist-rail-empty"
        className="flex flex-col items-stretch gap-2 px-3 py-4"
      >
        <p
          className="text-[12px] leading-snug"
          style={{ color: "var(--text-secondary)" }}
        >
          尚未追蹤任何標的
        </p>
        <p
          className="text-[11px]"
          style={{ color: "var(--text-muted)" }}
        >
          進入個股頁可加入自選。
        </p>
      </div>
    );
  }

  // WatchlistItemResponse currently ships only id / symbol / stock_name /
  // created_at — price + change are not yet on the backend contract, so
  // QuoteRow will render em-dashes for the numeric columns. Same convention
  // used by command-palette search results; flagged as a follow-up in the
  // PR body.
  return (
    <ul className="flex flex-col" role="list">
      {items.map((it) => (
        <li key={it.symbol}>
          <QuoteRow
            variant="compact"
            symbol={it.symbol}
            name={it.stock_name ?? undefined}
            href={`/stocks/${encodeURIComponent(it.symbol)}`}
          />
        </li>
      ))}
    </ul>
  );
}

export default WatchlistRail;
