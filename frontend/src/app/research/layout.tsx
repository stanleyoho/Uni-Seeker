"use client";

import { SubTabs } from "@/components/stratos/sub-tabs";
import { useI18n } from "@/i18n/context";

export default function ResearchLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();

  // Unified `/research` tab consolidates the legacy `篩選器` + `訊號掃描`
  // into one Scan workflow (templates + condition builder + numeric
  // thresholds + tooltips). The standalone `/research/scanner` route now
  // redirects to `/research` — see `frontend/src/app/research/scanner/page.tsx`.
  const tabs = [
    { href: "/research", label: t.nav.scan ?? "掃描" },
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
