"use client";

/**
 * /portfolio — Portfolio dashboard (PORT-001).
 *
 * History: this route previously rendered WATCH-001 (the watchlist UI),
 * which collided with the header nav's "Portfolio" intent and made
 * the legitimate portfolio dashboard unreachable. The watchlist has
 * been moved to /portfolio/watchlist (see `./watchlist/page.tsx`); this
 * file now owns the actual portfolio summary view that aggregates:
 *
 *   - KPI tiles  → reused from `HoldingsKpiRow` (total market value,
 *                  cost basis, unrealized P&L, etc).
 *   - Positions  → reused from `HoldingsTableResponsive`.
 *   - Watchlist  → compact preview pulled from the same backend
 *                  `useWatchlistApi()` source as /portfolio/watchlist.
 *
 * Unauthenticated users see a CTA to sign in instead of a 401 banner.
 *
 * Data flow mirrors /holdings (which also uses HoldingsKpiRow +
 * HoldingsTableResponsive); positions here are scoped to all accounts
 * so the dashboard stays a single-screen overview. Drill-down is via
 * the explicit `MANAGE HOLDINGS` CTA → /holdings.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import {
  HoldingsKpiRow,
  HoldingsTableResponsive,
  PositionsEmptyState,
} from "@/components/holdings";
import {
  useHoldingPositions,
  useUserHoldingSummary,
} from "@/hooks/use-holdings";
import { useWatchlistApi } from "@/hooks/use-watchlist-api";

const WATCHLIST_PREVIEW_LIMIT = 6;

export default function PortfolioDashboardPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();

  // ── Auth gate ──────────────────────────────────────────────────────
  // Backend portfolio + watchlist endpoints require auth. We surface a
  // friendly CTA rather than letting `apiFetch` 401-banner. We *do*
  // unconditionally call the data hooks below so the hook ordering
  // stays stable across the auth transition (rules-of-hooks). The
  // hooks themselves short-circuit when there's no token.
  const {
    data: summary,
    isLoading: summaryLoading,
  } = useUserHoldingSummary(undefined);
  const {
    data: positionsRes,
    isLoading: positionsLoading,
  } = useHoldingPositions(undefined);
  const {
    data: watchlistItems = [],
    isLoading: watchlistLoading,
  } = useWatchlistApi();

  if (!authLoading && !user) {
    return (
      <main className="relative flex-1 bg-[var(--background)]">
        <AmbientBackground />
        <div className="relative z-10 max-w-[1440px] mx-auto px-4 lg:px-6 py-12">
          <GlassPanel className="py-24 text-center">
            <h1 className="text-2xl font-bold tracking-tighter text-[var(--foreground)] uppercase mb-2">
              Portfolio Dashboard
            </h1>
            <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-[0.2em]">
              請先登入查看投資組合
            </p>
            <p className="text-[10px] text-[var(--text-muted)] mt-2 uppercase">
              Sign in to view your KPIs, positions, and watchlist.
            </p>
            <Link href="/login" className="inline-block mt-6">
              <ClippedButton variant="red-solid" size="md">
                GO TO LOGIN
              </ClippedButton>
            </Link>
          </GlassPanel>
        </div>
      </main>
    );
  }

  const positions = (positionsRes?.positions ?? []).map((p) => ({
    ...p,
    qty: p.qty ?? "0",
    realized_pnl: p.realized_pnl ?? "0",
  }));

  const watchlistPreview = watchlistItems.slice(0, WATCHLIST_PREVIEW_LIMIT);
  const watchlistOverflow = Math.max(
    0,
    watchlistItems.length - WATCHLIST_PREVIEW_LIMIT,
  );

  return (
    <main className="relative flex-1 overflow-y-auto bg-[var(--background)]">
      <AmbientBackground />
      <div className="relative z-10 max-w-[1440px] mx-auto px-4 lg:px-6 py-6 space-y-6 animate-fade-in">
        {/* Title row */}
        <div className="flex items-end justify-between border-b border-[var(--border-subtle)] pb-4">
          <div>
            <h1
              className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase"
              style={{ letterSpacing: "-0.04em" }}
            >
              {t.nav?.portfolio ?? "Portfolio"}
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              Aggregate snapshot · {positions.length} positions ·{" "}
              {watchlistItems.length} watching
            </p>
          </div>
          <div className="hidden md:flex gap-2">
            <Link href="/holdings">
              <ClippedButton variant="cyan-ghost" size="sm">
                MANAGE HOLDINGS
              </ClippedButton>
            </Link>
            <Link href="/portfolio/watchlist">
              <ClippedButton variant="red-solid" size="sm">
                OPEN WATCHLIST
              </ClippedButton>
            </Link>
          </div>
        </div>

        {/* KPI tiles — reuse the holdings KPI row */}
        <section aria-label="Portfolio KPIs">
          <HoldingsKpiRow
            summary={summary}
            loading={summaryLoading}
            displayCurrency="TWD"
            byCurrencyLabel="幣別分布"
          />
        </section>

        {/* Positions table */}
        <section aria-label="Positions">
          <GlassPanel title="POSITIONS" noPadding>
            {positionsLoading ? (
              <div className="py-16 text-center text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-bold">
                Loading positions…
              </div>
            ) : positions.length === 0 ? (
              <div className="p-6">
                {/* Empty-state CTA: trade entry lives on the dedicated
                    /holdings page (account context + currency switcher
                    are needed). Bounce the user there rather than
                    duplicating the modal at the dashboard level. */}
                <PositionsEmptyState
                  onAddTrade={() => router.push("/holdings")}
                />
              </div>
            ) : (
              <HoldingsTableResponsive
                positions={positions}
                loading={false}
              />
            )}
          </GlassPanel>
        </section>

        {/* Watchlist preview */}
        <section aria-label="Watchlist preview">
          <GlassPanel
            title={`WATCHLIST · ${watchlistItems.length}`}
            noPadding
          >
            {watchlistLoading ? (
              <div className="py-12 text-center text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-bold">
                Loading watchlist…
              </div>
            ) : watchlistItems.length === 0 ? (
              <div className="py-12 text-center">
                <p className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-bold">
                  No symbols on watch yet
                </p>
                <Link
                  href="/portfolio/watchlist"
                  className="inline-block mt-4"
                >
                  <ClippedButton variant="cyan-ghost" size="sm">
                    OPEN WATCHLIST
                  </ClippedButton>
                </Link>
              </div>
            ) : (
              <div>
                <ul className="divide-y divide-[var(--border-subtle)]">
                  {watchlistPreview.map((item) => (
                    <li
                      key={item.symbol}
                      className="flex items-center justify-between px-4 py-3 hover:bg-[var(--card-hover)] transition-colors"
                    >
                      <div className="min-w-0">
                        <Link
                          href={`/stocks/${encodeURIComponent(item.symbol)}`}
                          className="text-sm font-bold text-[var(--foreground)] tabular-nums hover:text-[var(--accent-cyan)] transition-colors"
                        >
                          {item.symbol.split(".")[0]}
                        </Link>
                        {item.stock_name && (
                          <span className="ml-3 text-xs text-[var(--text-secondary)] truncate">
                            {item.stock_name}
                          </span>
                        )}
                      </div>
                      <Link
                        href={`/stocks/${encodeURIComponent(item.symbol)}`}
                        className="text-[10px] font-bold uppercase tracking-widest text-[var(--accent-cyan)] hover:underline shrink-0 ml-4"
                      >
                        ANALYZE
                      </Link>
                    </li>
                  ))}
                </ul>
                <div className="px-4 py-3 border-t border-[var(--border-subtle)] flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-muted)]">
                    {watchlistOverflow > 0
                      ? `+${watchlistOverflow} more`
                      : `Showing all ${watchlistItems.length}`}
                  </span>
                  <Link
                    href="/portfolio/watchlist"
                    className="text-[10px] font-bold uppercase tracking-widest text-[var(--accent-cyan)] hover:underline"
                  >
                    OPEN WATCHLIST →
                  </Link>
                </div>
              </div>
            )}
          </GlassPanel>
        </section>

        {/* Mobile action row — desktop has the actions in the header */}
        <div className="flex md:hidden gap-2">
          <Link href="/holdings" className="flex-1">
            <ClippedButton variant="cyan-ghost" size="md" className="w-full">
              MANAGE HOLDINGS
            </ClippedButton>
          </Link>
          <Link href="/portfolio/watchlist" className="flex-1">
            <ClippedButton variant="red-solid" size="md" className="w-full">
              OPEN WATCHLIST
            </ClippedButton>
          </Link>
        </div>
      </div>
    </main>
  );
}
