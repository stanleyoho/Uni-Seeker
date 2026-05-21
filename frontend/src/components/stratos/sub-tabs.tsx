"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface SubTab {
  href: string;
  label: string;
}

export function SubTabs({ tabs }: { tabs: SubTab[] }) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (tabs[0]?.href === href) {
      return pathname === href;
    }
    return pathname.startsWith(href);
  };

  return (
    <div
      className="flex items-center gap-1 px-6 py-2"
      style={{
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={`px-4 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
            isActive(tab.href)
              ? "text-[var(--foreground)]"
              : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
          }`}
          style={{
            clipPath: isActive(tab.href)
              ? "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))"
              : undefined,
            background: isActive(tab.href) ? "var(--card-hover)" : undefined,
          }}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
