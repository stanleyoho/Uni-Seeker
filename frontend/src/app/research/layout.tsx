"use client";

import { SubTabs } from "@/components/stratos/sub-tabs";
import { useI18n } from "@/i18n/context";

export default function ResearchLayout({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();

  // Unified `/research` tab consolidates the legacy `篩選器` + `訊號掃描`
  // into one Scan workflow (templates + condition builder + numeric
  // thresholds + tooltips). The standalone `/research/scanner` route now
  // redirects to `/research` — see `frontend/src/app/research/scanner/page.tsx`.
  //
  // Route-consolidation refactor: the `比較` tab no longer points to the
  // sibling `/research/compare` route — that page is now a permanent
  // redirect to `/research?tab=compare`. The CompareTabPanel is mounted
  // by `/research/page.tsx` when `?tab=compare` is present. Low-Base
  // stays as its own route because it has nested dynamic sub-routes
  // (e.g. `/research/low-base/[symbol]`) that would be awkward to
  // flatten into a single page-level switch.
  const tabs = [
    {
      href: "/research",
      label: t.nav.scan ?? "掃描",
      defaultWhenQueryMissing: true,
    },
    { href: "/research/low-base", label: t.nav.lowBase },
    {
      href: "/research?tab=compare",
      label: t.nav.compare,
      activeQuery: { key: "tab", value: "compare" },
    },
    // 四大買賣點 — TW-only daily Best-Four-Point board, hosted as a
    // `?tab=` query-multiplex view on `/research` (same pattern as
    // Compare). Hard-coded label until the i18n bundle gains a key.
    {
      href: "/research?tab=best-four-point",
      label: "四大買賣點",
      activeQuery: { key: "tab", value: "best-four-point" },
    },
    // Composable Query DSL filter builder (A2) — arbitrarily-nested
    // AND/OR groups of field/comparator/value conditions, compiled onto
    // the screener engine. Hosted as a `?tab=` query-multiplex view.
    {
      href: "/research?tab=dsl",
      label: "進階篩選",
      activeQuery: { key: "tab", value: "dsl" },
    },
    // ETF premium/discount monitor (twetf.com-inspired). Hard-coded
    // label until the i18n bundle gains an `etfArbitrage` key —
    // keeping it inline keeps this PR self-contained.
    { href: "/research/etf-arbitrage", label: "ETF 折溢價" },
  ];

  return (
    <>
      <SubTabs tabs={tabs} />
      {children}
    </>
  );
}
