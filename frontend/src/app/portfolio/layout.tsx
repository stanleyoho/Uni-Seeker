"use client";

import { SubTabs } from "@/components/stratos/sub-tabs";
import { useI18n } from "@/i18n/context";

export default function PortfolioLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();

  // Sub-tab order = drill direction. Dashboard first (the new
  // /portfolio root view, PORT-001), then the deeper tools.
  // `Watchlist` moved from `/portfolio` to `/portfolio/watchlist` so
  // the root URL can host the actual portfolio dashboard.
  const tabs = [
    { href: "/portfolio", label: t.nav?.portfolio || "Dashboard" },
    { href: "/portfolio/watchlist", label: t.nav?.watchlist || "Watchlist" },
    { href: "/portfolio/backtest", label: t.nav?.backtest || "Backtest" },
    { href: "/portfolio/test", label: t.nav?.portfolioTest || "Portfolio Test" },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[var(--background)]">
      <SubTabs tabs={tabs} />
      {children}
    </div>
  );
}
