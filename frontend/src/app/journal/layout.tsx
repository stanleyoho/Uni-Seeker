/**
 * Server Component layout for /journal/*. Was `"use client"` purely so
 * it could call `useI18n()` for tab labels — but every label here is a
 * fixed Chinese string Stanley already hard-coded. Hoisting the labels
 * up makes the layout RSC, shrinking the client bundle for every
 * journal sub-route by the size of the i18n payload it would otherwise
 * pull in.
 *
 * `SubTabs` itself is a Client Component
 * (`usePathname`/`useSearchParams`), which is fine — an RSC can render
 * a Client Component child.
 *
 * Route-consolidation refactor: the three sub-routes that used to live
 * under /journal/{accounts,groups} were flattened into the root page
 * via `?tab=` query params (the existing routes still exist as
 * permanent redirects for external links). The relabel `總覽 → 日誌`
 * mirrors the user-facing taxonomy: this is the trade-log surface,
 * not a portfolio overview (which lives under /portfolio).
 */

import { SubTabs } from "@/components/stratos/sub-tabs";

const TABS = [
  { href: "/journal", label: "日誌", defaultWhenQueryMissing: true },
  {
    href: "/journal?tab=accounts",
    label: "帳戶",
    activeQuery: { key: "tab", value: "accounts" },
  },
  {
    href: "/journal?tab=groups",
    label: "群組",
    activeQuery: { key: "tab", value: "groups" },
  },
];

export default function JournalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[var(--background)]">
      <SubTabs tabs={TABS} />
      {children}
    </div>
  );
}
