"use client";
import { SubTabs } from "@/components/stratos/sub-tabs";
import { useI18n } from "@/i18n/context";

export default function PortfolioLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const tabs = [
    { href: "/portfolio", label: t.nav.watchlist },
    { href: "/portfolio/backtest", label: t.nav.backtest },
    { href: "/portfolio/test", label: t.portfolio?.title || "Portfolio Test" },
  ];
  return (
    <>
      <SubTabs tabs={tabs} />
      {children}
    </>
  );
}
