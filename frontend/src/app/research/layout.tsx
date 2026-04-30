"use client";

import { SubTabs } from "@/components/stratos/sub-tabs";
import { useI18n } from "@/i18n/context";

export default function ResearchLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();

  const tabs = [
    { href: "/research", label: t.nav.screener },
    { href: "/research/scanner", label: t.nav.scanner },
    { href: "/research/low-base", label: t.nav.lowBase },
    { href: "/research/compare", label: t.nav.compare },
  ];

  return (
    <>
      <SubTabs tabs={tabs} />
      {children}
    </>
  );
}
