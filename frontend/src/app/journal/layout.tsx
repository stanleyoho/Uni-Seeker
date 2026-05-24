"use client";

import { SubTabs } from "@/components/stratos/sub-tabs";

export default function JournalLayout({ children }: { children: React.ReactNode }) {
  const tabs = [
    { href: "/journal", label: "總覽" },
    { href: "/journal/accounts", label: "帳戶" },
    { href: "/journal/groups", label: "群組" },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[var(--background)]">
      <SubTabs tabs={tabs} />
      {children}
    </div>
  );
}
