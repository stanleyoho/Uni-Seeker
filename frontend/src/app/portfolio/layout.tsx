"use client";

import { SubTabs } from "@/components/stratos/sub-tabs";
import { useI18n } from "@/i18n/context";

export default function PortfolioLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();

  // Route-consolidation refactor: portfolio sub-tabs are pruned to the
  // three surfaces a day-trader actually visits — `總覽` (this
  // section's dashboard root), `Watchlist` (full management view; the
  // always-visible WatchlistRail handles the lightweight at-a-glance
  // need), and `帳戶` which jumps to `/holdings` since multi-account /
  // multi-currency reconciliation lives there. Backtest + Portfolio
  // Test were dropped from the nav (the routes still exist + are
  // reachable via deep links or the command palette — they're niche
  // power-user surfaces and the primary nav was beginning to crowd
  // the SubTabs strip).
  //
  // 帳戶 → /holdings: yes, the global top-nav also has "持倉" pointing
  // at /holdings. That's intentional — the duplication is "two doors,
  // same room", and routes the user from any portfolio sub-page back
  // to the canonical account/positions surface without a
  // context-switch loop.
  const tabs = [
    { href: "/portfolio", label: t.nav?.portfolioOverview || "總覽" },
    { href: "/portfolio/watchlist", label: t.nav?.watchlist || "Watchlist" },
    { href: "/holdings", label: t.nav?.accounts || "帳戶" },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[var(--background)]">
      <SubTabs tabs={tabs} />
      {children}
    </div>
  );
}
