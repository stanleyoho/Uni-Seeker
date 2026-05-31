/**
 * Server Component layout for /journal/*. Was `"use client"` purely so
 * it could call `useI18n()` for tab labels — but every label here is a
 * fixed Chinese string Stanley already hard-coded. Hoisting the labels
 * up makes the layout RSC, shrinking the client bundle for every
 * journal sub-route by the size of the i18n payload it would otherwise
 * pull in.
 *
 * `SubTabs` itself is a Client Component (`usePathname`), which is
 * fine — an RSC can render a Client Component child.
 */

import { SubTabs } from "@/components/stratos/sub-tabs";

const TABS = [
  { href: "/journal", label: "總覽" },
  { href: "/journal/accounts", label: "帳戶" },
  { href: "/journal/groups", label: "群組" },
];

export default function JournalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[var(--background)]">
      <SubTabs tabs={TABS} />
      {children}
    </div>
  );
}
